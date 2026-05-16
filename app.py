import json
import os
import time
from typing import Any

from dotenv import load_dotenv
load_dotenv()  # Load .env file before reading config

import httpx
import mlflow
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from mlflow.entities import SpanType
from openai import OpenAI

from tools import get_default_registry, UnifiedToolRegistry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools
from tools.builtin.canvas_tools import set_canvas_manager  # Canvas tools
from tools.builtin.agent_tools import set_agent_context, get_fork_manager, get_agent_runner, AGENT_TYPES
from tools.builtin.skill_tools import *  # noqa: F401,F403 — register Skill tool
from tools.mcp import MCPToolManager, MCPConfig
from automation import CronStore, CronScheduler
from automation.webhook import WebhookStore, WebhookExecutor, init_webhooks
from providers import ProviderRegistry, register_default_providers
from gateway import GATEWAY_VERSION, get_version_headers, validate_client_version, get_changelog
from core import run_tool_loop, clean_orphan_tool_messages, ToolExecutor, is_safe
from sessions import SessionManager, TokenCalculator, CompactionManager, CompactionConfig, BudgetManager, estimate_tokens_simple, ResilientExecutor, classify_error, get_retry_config, calculate_delay, ErrorKind, PermissionMode, PermissionRuleKind, HookEvent, HookMatcher, MultiSourceRuleManager, PermissionAuditor, PermissionRule, PermissionResult, RuleSource
from sessions.vector_memory import VectorMemoryStore
from skills import SkillLoader, default_skill_dirs
from channels import ChannelRouter
from canvas import CanvasManager, CanvasChannel
from core import PromptBuilder, MemoryLoader
from acp import AgentControlPlane, AcpConfig

# ===== Config =====
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "agentcraft-gateway")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-default")

# Concurrency / Rate Limiting
MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_OLLAMA", "10"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ===== Logging (写入文件) =====
import logging

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "gateway.log")
CHAT_LOG_FILE = os.path.join(LOG_DIR, "chat.log")

logger = logging.getLogger("gateway")
logger.setLevel(logging.DEBUG)

chat_logger = logging.getLogger("chat")
chat_logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

if not chat_logger.handlers:
    chat_file_handler = logging.FileHandler(CHAT_LOG_FILE, mode="a", encoding="utf-8")
    chat_file_handler.setLevel(logging.INFO)
    chat_file_handler.setFormatter(formatter)
    chat_logger.addHandler(chat_file_handler)

# ===== MLflow =====
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(MLFLOW_EXPERIMENT)
mlflow.openai.autolog(log_traces=False)

# ===== LLM Client =====
client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    http_client=httpx.Client(
        trust_env=False,
        timeout=300,
    ),
)

# ===== Concurrency & Rate Limiting =====
_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)
_rate_limit_buckets: dict[str, list[float]] = {}
_rate_limit_lock = asyncio.Lock()


# ===== MCP Tool Manager =====
_mcp_manager: MCPToolManager | None = None
_unified_registry: UnifiedToolRegistry | None = None

# ===== Session Manager =====
_session_manager = SessionManager()

# ===== Skills =====
_skill_loader = SkillLoader(default_skill_dirs())
_skill_loader.load()
set_skill_loader(_skill_loader)  # Set skill loader for Skill tool

# ===== Canvas =====
_canvas_manager: CanvasManager | None = None
_canvas_channel: CanvasChannel | None = None

# ===== Compaction =====
_compaction_manager: CompactionManager | None = None

# ===== Budget =====
_budget_manager: BudgetManager | None = None

# ===== Enhanced Permission =====
_permission_rule_manager: MultiSourceRuleManager | None = None
_permission_auditor: PermissionAuditor | None = None

# ===== Memory =====
_memory_store: VectorMemoryStore | None = None
_memory_loader: MemoryLoader | None = None
_prompt_builder: PromptBuilder | None = None

# ===== ACP (Agent Control Plane) =====
_acp: AgentControlPlane | None = None

# ===== Error Recovery =====
_recovery_executor: ResilientExecutor | None = None

# ===== Channels =====
_channel_router = ChannelRouter()
_canvas_channel: CanvasChannel | None = None

# ===== Provider Registry =====
_provider_registry: ProviderRegistry | None = None

# ===== Webhook =====
_webhook_store: WebhookStore | None = None
_webhook_executor: WebhookExecutor | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize MCP servers and channels on startup, shut down on exit."""
    global _mcp_manager, _unified_registry, _canvas_manager, _canvas_channel

    _app.state.session_manager = _session_manager
    _skill_loader.load()
    _app.state.skill_loader = _skill_loader

    # Canvas initialization (before channels, so tools can use it)
    _canvas_manager = CanvasManager()
    _app.state.canvas_manager = _canvas_manager
    set_canvas_manager(_canvas_manager)
    logger.info("[Canvas] CanvasManager initialized")

    # MCP initialization
    config = MCPConfig.load()
    if config.enabled and config.get_enabled_servers():
        _mcp_manager = MCPToolManager()
        await _mcp_manager.initialize(config)
        _unified_registry = UnifiedToolRegistry(
            get_default_registry(), _mcp_manager
        )
        _app.state.mcp_manager = _mcp_manager
        _app.state.unified_registry = _unified_registry
    else:
        _unified_registry = UnifiedToolRegistry(get_default_registry())
        _app.state.unified_registry = _unified_registry

    # Compaction Manager initialization
    global _compaction_manager
    compaction_config = CompactionConfig()
    _compaction_manager = CompactionManager(
        session_manager=_session_manager,
        llm_client=client,
        config=compaction_config,
    )
    _app.state.compaction_manager = _compaction_manager
    logger.info("[Compaction] CompactionManager initialized")

    # Budget Manager initialization
    global _budget_manager
    _budget_manager = BudgetManager()
    _app.state.budget_manager = _budget_manager
    logger.info("[Budget] BudgetManager initialized")

    # Enhanced Permission initialization
    global _permission_rule_manager, _permission_auditor
    _permission_rule_manager = MultiSourceRuleManager()
    _permission_auditor = PermissionAuditor()
    _app.state.permission_rule_manager = _permission_rule_manager
    _app.state.permission_auditor = _permission_auditor
    logger.info("[Permission] MultiSourceRuleManager and PermissionAuditor initialized")

    # Error Recovery initialization
    global _recovery_executor
    _recovery_executor = ResilientExecutor()
    # Wire compaction callback for prompt_too_long recovery
    async def _recovery_compact(messages):
        calculator = TokenCalculator()
        target = int((session.context_window or 64000) * 0.3)
        return await _compaction_manager.compact(
            session_id="recovery",
            messages=messages,
            level=3,  # Reactive
            calculator=calculator,
            target_tokens=target,
        )
    _recovery_executor.set_compaction_callback(_recovery_compact)
    _app.state.recovery_executor = _recovery_executor
    logger.info("[Recovery] ResilientExecutor initialized")

    # Fork Manager initialization
    from sessions import ForkManager, TokenCalculator
    fork_manager = ForkManager(
        session_manager=_session_manager,
        token_calculator=TokenCalculator(),
        canvas_manager=_canvas_manager,
    )
    set_agent_context(
        llm_client=client,
        registry=_unified_registry,
        fork_manager=fork_manager,
        canvas_manager=_canvas_manager,
    )
    logger.info("[Fork] ForkManager initialized")

    # ACP (Agent Control Plane) initialization for multi-agent tasks
    global _acp
    acp_config = AcpConfig(
        max_children=10,
        default_timeout=180,
        context_inheritance_limit=32000,
        recursion_protection=True,
    )
    _acp = AgentControlPlane(
        llm_client=client,
        registry=_unified_registry,
        session_manager=_session_manager,
        fork_manager=fork_manager,
        config=acp_config,
        model="deepseek-chat",
    )
    _app.state.acp = _acp
    logger.info("[ACP] AgentControlPlane initialized: max_children=10, timeout=180s")

    # Memory initialization (VectorMemoryStore)
    global _memory_store
    from sessions.vector_memory import VectorMemoryStore, MockEmbeddingModel
    _memory_store = VectorMemoryStore(embedding_model=MockEmbeddingModel())
    _app.state.memory_store = _memory_store
    logger.info("[Memory] VectorMemoryStore initialized")

    # Core PromptBuilder (uses MemoryLoader with task-based retrieval)
    global _prompt_builder, _memory_loader
    _memory_loader = MemoryLoader(store=_memory_store)
    _prompt_builder = PromptBuilder(
        skill_loader=_skill_loader,
        memory_loader=_memory_loader,
    )
    _app.state.prompt_builder = _prompt_builder
    logger.info("[Core] PromptBuilder initialized with task-based memory retrieval")

    # Initialize channels - Canvas only
    _canvas_channel = CanvasChannel(_canvas_manager)
    _channel_router.register(_canvas_channel)
    _app.include_router(_canvas_channel.get_router())
    logger.info("[Canvas] CanvasChannel registered at /canvas")

    # Provider Registry initialization (multi-provider support with fallback)
    global _provider_registry
    _provider_registry = register_default_providers()
    _app.state.provider_registry = _provider_registry
    if _provider_registry:
        status = _provider_registry.get_status_summary()
        logger.info(f"[ProviderRegistry] Initialized: {status}")

    # Webhook initialization (external event triggers)
    global _webhook_store, _webhook_executor
    _webhook_store = WebhookStore()
    _webhook_executor = WebhookExecutor(_webhook_store, get_agent_runner)
    _app.state.webhook_store = _webhook_store
    _app.state.webhook_executor = _webhook_executor
    logger.info("[Webhook] WebhookExecutor initialized")

    await _channel_router.start_all()

    yield

    # Cleanup
    await _channel_router.stop_all()
    if _mcp_manager:
        await _mcp_manager.shutdown()


app = FastAPI(title="Ollama MLflow Gateway", lifespan=lifespan)


# ===== Version Middleware =====
from starlette.middleware.base import BaseHTTPMiddleware

class VersionMiddleware(BaseHTTPMiddleware):
    """Add version headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        # Check client version header
        client_version = request.headers.get("X-Client-Version")
        is_valid, message = validate_client_version(client_version)

        if not is_valid:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"error": message, "gateway_version": GATEWAY_VERSION},
                headers=get_version_headers(),
            )

        # Process request
        response = await call_next(request)

        # Add version headers to response
        for key, value in get_version_headers().items():
            response.headers[key] = value

        return response

app.add_middleware(VersionMiddleware)


async def _check_rate_limit(request: Request) -> None:
    """Raise HTTPException(429) if the client IP has exceeded the rate limit."""
    if not RATE_LIMIT_ENABLED:
        return
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW

    async with _rate_limit_lock:
        timestamps = _rate_limit_buckets.get(client_ip, [])
        timestamps = [t for t in timestamps if t > window_start]
        if len(timestamps) >= RATE_LIMIT_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": {
                        "message": "Rate limit exceeded. Try again later.",
                        "type": "rate_limit_error",
                    }
                },
            )
        timestamps.append(now)
        _rate_limit_buckets[client_ip] = timestamps


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI,
        "llm_base_url": LLM_BASE_URL,
        "gateway_version": GATEWAY_VERSION,
    }


@app.get("/version")
def get_version() -> dict[str, Any]:
    """Get gateway version info."""
    return get_changelog()


@app.get("/version/changelog")
def get_version_changelog() -> dict[str, Any]:
    """Get full version changelog."""
    return get_changelog()


@app.get("/version/migrate")
def get_version_migration(from_version: str = "0.8.0", to_version: str = GATEWAY_VERSION) -> dict[str, Any]:
    """Get migration guide between versions."""
    return get_migration_guide(from_version, to_version)


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    """Return available models."""
    return {
        "object": "list",
        "data": [
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
            {"id": "deepseek-reasoner", "object": "model", "owned_by": "deepseek"},
        ],
    }


# ===== Session REST Endpoints =====


@app.post("/v1/sessions")
async def create_session(request: Request) -> dict[str, Any]:
    body = await request.json()
    session = _session_manager.create_session(
        name=body.get("name", "Untitled"),
        model=body.get("model", "deepseek-chat"),
        system_prompt=body.get("system_prompt"),
        skills=body.get("skills", ""),
    )
    return session.to_dict()


@app.get("/v1/sessions")
def list_sessions(status: str = "active") -> list[dict[str, Any]]:
    return [s.to_dict() for s in _session_manager.list_sessions(status)]


@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = _session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.patch("/v1/sessions/{session_id}")
async def update_session(session_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    session = _session_manager.update_session(session_id, **body)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.delete("/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, str]:
    if not _session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@app.get("/v1/sessions/{session_id}/messages")
def get_session_messages(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _session_manager.get_messages_openai(session_id, limit)


@app.post("/v1/sessions/{session_id}/messages")
async def add_session_message(session_id: str, request: Request) -> dict[str, Any]:
    """Add a message directly to session (for testing/bulk operations)."""
    body = await request.json()
    session = _session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg = _session_manager.add_message(
        session_id=session_id,
        role=body.get("role", "user"),
        content=body.get("content", ""),
        tool_call_id=body.get("tool_call_id"),
        name=body.get("name"),
    )
    return {"id": msg.id, "token_count": msg.token_count}


@app.get("/v1/skills")
def list_skills() -> list[dict[str, Any]]:
    return [s.to_dict() for s in _skill_loader.list_skills()]


@app.get("/permission/rules")
def get_permission_rules() -> dict[str, Any]:
    """Get current permission rules."""
    if _permission_rule_manager is None:
        return {"error": "Permission rule manager not initialized"}

    rules = _permission_rule_manager.get_effective_rules()
    return {
        "rules": [r.to_dict() for r in rules],
        "source_stats": _permission_rule_manager.get_source_stats(),
    }


@app.post("/permission/rules")
async def add_permission_rule(request: Request) -> dict[str, Any]:
    """Add a permission rule."""
    if _permission_rule_manager is None:
        raise HTTPException(status_code=500, detail="Permission manager not initialized")

    body = await request.json()
    pattern = body.get("pattern")
    action = body.get("action")  # "allow", "deny", "ask"
    reason = body.get("reason")

    if not pattern or not action:
        raise HTTPException(status_code=400, detail="Missing pattern or action")

    kind_map = {
        "allow": PermissionRuleKind.ALWAYS_ALLOW,
        "deny": PermissionRuleKind.ALWAYS_DENY,
        "ask": PermissionRuleKind.ALWAYS_ASK,
    }

    kind = kind_map.get(action.lower())
    if kind is None:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    rule = PermissionRule(
        kind=kind,
        pattern=pattern,
        source=RuleSource.COMMAND,
        reason=reason,
    )
    _permission_rule_manager.add_rule(rule)

    logger.info(f"[Permission] Added rule: {pattern} → {action}")
    return {"success": True, "pattern": pattern, "action": action}


@app.get("/permission/logs")
def get_permission_logs(session_id: str | None = None) -> list[dict[str, Any]]:
    """Get permission audit logs."""
    if _permission_auditor is None:
        return [{"error": "Permission auditor not initialized"}]

    return _permission_auditor.get_logs(session_id)


# ===== Memory API =====

from pydantic import BaseModel


class MemorySaveRequest(BaseModel):
    """Request body for memory save."""
    content: str
    name: str | None = None
    memory_type: str | None = None


@app.post("/memory/save")
def save_memory(request: MemorySaveRequest) -> dict[str, str]:
    """Save a memory entry."""
    if _memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    # Infer or parse type
    m_type = request.memory_type or "project"

    # Generate name if not provided
    name = request.name or request.content[:30].replace(" ", "-").lower()

    # Save to VectorMemoryStore
    _memory_store.save(name, m_type, request.content)
    return {"status": "saved", "name": name, "type": m_type}


@app.get("/memory/list")
def list_memories() -> dict[str, Any]:
    """List all memories (return MEMORY.md content)."""
    if _memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    index = _memory_store.get_index_content()
    entries = _memory_store.list()
    return {
        "index": index,
        "count": len(entries),
        "memories": [{"name": e.name, "type": e.type, "description": e.content[:100]} for e in entries],
    }


@app.get("/memory/{name}")
def get_memory(name: str) -> dict[str, Any]:
    """Get a specific memory."""
    if _memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    entry = _memory_store.load(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Memory not found: {name}")

    return {
        "name": entry.name,
        "type": entry.type,
        "content": entry.content,
        "created_at": entry.created_at,
    }


@app.get("/memory/search")
def search_memory(query: str, mode: str = "hybrid", limit: int = 10) -> dict[str, Any]:
    """Search memories (FTS, vector, or hybrid)."""
    if _memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    if mode == "fts":
        results = _memory_store.search_fts(query, limit)
    elif mode == "vector":
        results = _memory_store.search_vector(query, limit)
    else:
        results = _memory_store.search_hybrid(query, limit)

    return {
        "query": query,
        "mode": mode,
        "count": len(results),
        "results": [{"name": e.name, "type": e.type, "score": e.similarity, "content": e.content[:200]} for e in results],
    }


@app.delete("/memory/{name}")
def delete_memory(name: str) -> dict[str, str]:
    """Delete a memory."""
    if _memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    if _memory_store.delete(name):
        return {"status": "deleted", "name": name}
    else:
        raise HTTPException(status_code=404, detail=f"Memory not found: {name}")


# ===== ACP API =====

class AcpSpawnRequest:
    """Request body for spawning a child agent."""
    task: str
    agent_type: str = "general-purpose"
    timeout: int = 180


@app.post("/acp/spawn")
async def acp_spawn(request: Request) -> dict[str, Any]:
    """Spawn a child agent to execute a task."""
    if _acp is None:
        raise HTTPException(status_code=500, detail="ACP not initialized")

    data = await request.json()
    task = data.get("task", "")
    agent_type = data.get("agent_type", "general-purpose")
    timeout = data.get("timeout", 180)

    if not task:
        raise HTTPException(status_code=400, detail="Task is required")

    try:
        handle = _acp.spawn_child(
            task=task,
            agent_type=agent_type,
            timeout=timeout,
        )
        return {
            "child_id": handle.child_id,
            "task": handle.task,
            "agent_type": handle.agent_type,
            "state": handle.state.value,
            "started_at": handle.started_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/acp/status")
def acp_status() -> dict[str, Any]:
    """Get ACP status snapshot."""
    if _acp is None:
        raise HTTPException(status_code=500, detail="ACP not initialized")

    return _acp.get_status()


@app.get("/acp/children")
def acp_list_children() -> dict[str, Any]:
    """List all child agents."""
    if _acp is None:
        raise HTTPException(status_code=500, detail="ACP not initialized")

    status = _acp.get_status()
    return {"children": status.get("children", {})}


@app.post("/acp/wait")
async def acp_wait_all(request: Request) -> dict[str, str]:
    """Wait for all child agents to complete and return results."""
    if _acp is None:
        raise HTTPException(status_code=500, detail="ACP not initialized")

    data = await request.json()
    timeout = data.get("timeout", None)

    results = await _acp.wait_all(timeout=timeout)
    return results


@app.post("/acp/broadcast")
async def acp_broadcast(request: Request) -> dict[str, Any]:
    """Broadcast a message to all active child agents."""
    if _acp is None:
        raise HTTPException(status_code=500, detail="ACP not initialized")

    data = await request.json()
    message = data.get("message", "")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    count = _acp.broadcast(message)
    return {"broadcast_to": count, "message": message}


# ===== Cron API =====

_cron_store: CronStore | None = None
_cron_scheduler: CronScheduler | None = None


@app.on_event("startup")
async def init_cron():
    """Initialize cron scheduler."""
    global _cron_store, _cron_scheduler

    from automation import CronStore, CronScheduler
    from automation.scheduler import set_scheduler

    _cron_store = CronStore()
    _cron_scheduler = CronScheduler(
        store=_cron_store,
        agent_executor_factory=get_agent_runner,
    )
    _cron_scheduler.start()
    set_scheduler(_cron_scheduler)
    _app.state.cron_scheduler = _cron_scheduler
    logger.info("[Cron] Scheduler initialized")


@app.on_event("shutdown")
async def shutdown_cron():
    """Shutdown cron scheduler."""
    if _cron_scheduler:
        _cron_scheduler.stop()
        logger.info("[Cron] Scheduler stopped")


@app.get("/cron/status")
def cron_status() -> dict[str, Any]:
    """Get cron scheduler status."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")
    return _cron_scheduler.get_status()


@app.post("/test/canvas_push")
async def test_canvas_push(session_id: str, content: str = "Test message"):
    """Test canvas push directly."""
    if _canvas_manager is None:
        raise HTTPException(status_code=500, detail="Canvas manager not initialized")

    success = await _canvas_manager.push_update(
        session_id=session_id,
        content=content,
        mode="markdown",
        section="main",
        action="append",
    )
    return {"success": success, "session_id": session_id}


@app.get("/cron/jobs")
def cron_list_jobs() -> list[dict[str, Any]]:
    """List all cron jobs."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    jobs = _cron_scheduler.list_jobs()
    return [
        {
            "id": job.id,
            "name": job.name,
            "enabled": job.enabled,
            "schedule": {
                "kind": job.schedule.kind,
                "expr": getattr(job.schedule, "expr", None),
            },
            "task": job.task[:100],
            "status": job.state.status.value,
            "run_count": job.state.run_count,
            "error_count": job.state.error_count,
            "next_run": job.state.next_run_at,
            "last_run": job.state.last_run_at,
        }
        for job in jobs
    ]


@app.get("/cron/jobs/{job_id}")
def cron_get_job(job_id: str) -> dict[str, Any]:
    """Get cron job details."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    job = _cron_scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    runs = _cron_store.get_runs(job_id, limit=10)

    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": job.schedule.kind,
            "expr": getattr(job.schedule, "expr", None),
            "tz": getattr(job.schedule, "tz", None),
        },
        "task": job.task,
        "agent_type": job.agent_type,
        "timeout": job.timeout,
        "state": {
            "status": job.state.status.value,
            "run_count": job.state.run_count,
            "error_count": job.state.error_count,
            "last_result": job.state.last_result,
            "last_error": job.state.last_error,
        },
        "runs": runs,
    }


@app.post("/cron/jobs")
async def cron_create_job(request: Request) -> dict[str, Any]:
    """Create a new cron job."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    from automation.types import CronJob, CronExpressionSchedule, CronDelivery, DeliveryMode
    import uuid

    data = await request.json()

    # Required fields
    name = data.get("name")
    expr = data.get("expr")  # Cron expression
    task = data.get("task")

    if not name or not expr or not task:
        raise HTTPException(status_code=400, detail="name, expr, and task are required")

    job_id = f"cron-{uuid.uuid4().hex[:8]}"

    job = CronJob(
        id=job_id,
        name=name,
        schedule=CronExpressionSchedule(kind="cron", expr=expr, tz=data.get("tz")),
        task=task,
        agent_type=data.get("agent_type", "general-purpose"),
        timeout=data.get("timeout", 180),
        delivery=CronDelivery(
            mode=DeliveryMode(data.get("delivery_mode", "none")),
            channel=data.get("delivery_channel"),
            to=data.get("delivery_to"),
        ),
    )

    created = _cron_scheduler.add_job(job)

    return {
        "id": created.id,
        "name": created.name,
        "enabled": created.enabled,
        "schedule": {"kind": "cron", "expr": expr},
        "task": created.task,
        "status": "created",
    }


@app.delete("/cron/jobs/{job_id}")
def cron_delete_job(job_id: str) -> dict[str, Any]:
    """Delete a cron job."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    if _cron_scheduler.delete_job(job_id):
        return {"deleted": job_id}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@app.patch("/cron/jobs/{job_id}/enable")
def cron_enable_job(job_id: str) -> dict[str, Any]:
    """Enable a cron job."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    if _cron_scheduler.enable_job(job_id):
        return {"enabled": job_id}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@app.patch("/cron/jobs/{job_id}/disable")
def cron_disable_job(job_id: str) -> dict[str, Any]:
    """Disable a cron job."""
    if _cron_scheduler is None:
        raise HTTPException(status_code=500, detail="Cron scheduler not initialized")

    if _cron_scheduler.disable_job(job_id):
        return {"disabled": job_id}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


# ===== Webhook API =====

# Webhook initialized in lifespan, no separate startup needed


@app.post("/webhook/{webhook_name}")
async def webhook_trigger(webhook_name: str, request: Request) -> dict[str, Any]:
    """Handle webhook trigger and execute agent task.

    Headers:
        X-Webhook-Signature: HMAC-SHA256 signature (if secret configured)

    Payload:
        task: Task description for agent (optional, auto-generated if missing)
        message: Alternative task field
        ... other custom fields

    Returns:
        Execution result or error
    """
    if _webhook_executor is None:
        raise HTTPException(status_code=500, detail="Webhook system not initialized")

    # Get raw body for signature validation
    raw_body = await request.body()

    # Parse JSON payload
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Get headers
    headers = dict(request.headers)

    # Execute
    result = await _webhook_executor.handle_webhook(
        webhook_name=webhook_name,
        payload=payload,
        headers=headers,
        raw_body=raw_body,
    )

    if "error" in result:
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=result["error"])
        elif result.get("status") == "disabled":
            raise HTTPException(status_code=403, detail=result["error"])
        elif result.get("status") == "signature_error":
            raise HTTPException(status_code=401, detail=result["error"])
        elif result.get("status") == "invalid_payload":
            raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/webhooks")
def list_webhooks() -> list[dict[str, Any]]:
    """List all registered webhooks."""
    if _webhook_store is None:
        raise HTTPException(status_code=500, detail="Webhook system not initialized")

    webhooks = _webhook_store.list_webhooks()
    return [
        {
            "name": w.name,
            "url": w.url,
            "enabled": w.enabled,
            "agent_type": w.agent_type,
            "has_secret": w.secret is not None,
        }
        for w in webhooks
    ]


@app.get("/webhooks/events")
def get_webhook_events(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent webhook events."""
    if _webhook_executor is None:
        raise HTTPException(status_code=500, detail="Webhook system not initialized")

    events = _webhook_executor.get_recent_events(limit)
    return [
        {
            "webhook_name": e.webhook_name,
            "trigger_id": e.trigger_id,
            "received_at": e.received_at,
            "signature_valid": e.signature_valid,
            "payload": e.payload,
        }
        for e in events
    ]


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Rate limit check (quick, no LLM)
    await _check_rate_limit(request)

    payload = await request.json()
    model = payload.get("model", "deepseek-chat")
    session_id = request.headers.get("X-Session-Id")
    stream = payload.get("stream", False)

    if _llm_semaphore.locked():
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "message": "Too many concurrent requests. Try again later.",
                    "type": "concurrency_limit_error",
                }
            },
        )

    if stream:
        # SSE streaming response with tool progress
        return StreamingResponse(
            _handle_streaming(request, client, payload, model, session_id),
            media_type="text/event-stream",
        )
    else:
        return await _handle_non_streaming(request, client, payload, model, session_id)


async def _handle_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
    session_id: str | None = None,
):
    """SSE streaming response with tool execution progress."""
    import asyncio

    # Initialize (similar to non-streaming setup)
    registry = _unified_registry or UnifiedToolRegistry(get_default_registry())
    user_tools = payload.get("tools")
    tools = user_tools if user_tools is not None else registry.list_tools()

    # Build messages (simplified)
    new_messages = list(payload.get("messages", []))
    if session_id:
        session = _session_manager.get_session(session_id)
        if session:
            max_tokens = session.context_window or 64000
            history = _session_manager.get_messages_with_limit(session_id, max_tokens)
            messages = history + new_messages
            # Build system prompt using core module (task-based memory retrieval)
            if _prompt_builder:
                system_prompt = _prompt_builder.build(
                    messages=messages,
                    goal=None,  # TODO: session.goal if available
                    session_system_prompt=session.system_prompt,
                )
                if system_prompt:
                    messages = _prompt_builder.insert_into_messages(messages, system_prompt)
        else:
            messages = new_messages
    else:
        messages = new_messages

    messages = clean_orphan_tool_messages(messages)
    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools", "stream")}

    # Yield initial event
    yield f"event: stream_request_start\ndata: {{\"model\": \"{model}\"}}\n\n"

    # Execute with ToolExecutor
    executor = ToolExecutor(
        registry=registry,
        session_id=session_id,
        canvas_manager=_canvas_manager,
    )

    # Save incoming messages to session
    if session_id:
        for msg in new_messages:
            _session_manager.add_message(
                session_id=session_id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
            )

    # Tool loop
    n_turns = 0
    while True:
        call_kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True, **kwargs}
        if tools:
            call_kwargs["tools"] = tools

        # Streaming LLM call
        full_content = ""
        tool_calls_list = []
        finish_reason = None

        try:
            async with _llm_semaphore:
                # Use streaming with direct client
                stream = await asyncio.to_thread(
                    llm_client.chat.completions.create, **call_kwargs
                )

                # Iterate over stream chunks
                for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue

                    # Stream content chunks
                    delta = choice.delta
                    if delta and delta.content:
                        full_content += delta.content
                        # Escape JSON and yield
                        escaped = delta.content.replace('"', '\\"').replace('\n', '\\n')
                        yield f"data: {{\"text\": \"{escaped}\"}}\n\n"

                    # Collect tool calls
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            # Accumulate tool call fragments
                            idx = tc.index
                            if idx >= len(tool_calls_list):
                                tool_calls_list.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if tc.id:
                                tool_calls_list[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_list[idx]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_list[idx]["function"]["arguments"] += tc.function.arguments

                    # Get finish reason
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

        except Exception as e:
            yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
            break

        # Build complete message
        message = {"role": "assistant", "content": full_content}
        if tool_calls_list:
            message["tool_calls"] = tool_calls_list
        messages.append(message)

        # Yield done event
        yield f"data: {{\"finish_reason\": \"{finish_reason or 'stop'}\"}}\n\n"

        # No tool calls - done
        if not tool_calls_list:
            break

        n_turns += 1
        if n_turns > 50:
            yield f"event: error\ndata: {{\"error\": \"Tool limit exceeded\"}}\n\n"
            break

        # Yield tool start events
        for tc in tool_calls_list:
            fn_name = tc["function"]["name"]
            yield f"event: tool_start\ndata: {{\"id\": \"{tc['id']}\", \"name\": \"{fn_name}\"}}\n\n"

        # Execute tools
        results = await executor.execute_tools(tool_calls_list)

        # Yield tool results and append to messages
        for tc in tool_calls_list:
            tc_id = tc["id"]
            tool_result = results.get(tc_id)
            if tool_result:
                if tool_result.error:
                    yield f"event: tool_error\ndata: {{\"id\": \"{tc_id}\", \"error\": \"{tool_result.error}\"}}\n\n"
                else:
                    result_preview = tool_result.content[:200] if len(tool_result.content) > 200 else tool_result.content
                    yield f"event: tool_result\ndata: {{\"id\": \"{tc_id}\", \"result\": \"{result_preview}\"}}\n\n"
                messages.append(tool_result.to_tool_message())

        yield f"event: turn_complete\ndata: {{\"turn\": {n_turns}, \"tools\": {len(tool_calls_list)}}}\n\n"

    # Save final messages
    if session_id:
        for msg in messages[len(new_messages):]:
            _session_manager.add_message(
                session_id=session_id,
                role=msg["role"],
                content=msg.get("content", ""),
                tool_calls=json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
                tool_call_id=msg.get("tool_call_id"),
            )


# ===== Slash command processing =====
def _process_slash_command(content: str) -> str | None:
    """Process slash commands like /goal. Returns response string or None."""
    content = content.strip()
    if not content.startswith("/"):
        return None

    parts = content.split(" ", 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command == "/goal":
        return "[Deprecated] Goal setting moved to session-level configuration."

    if command == "/permission":
        return "[Deprecated] Permission mode moved to session-level configuration. Available via session metadata."

    if command == "/hook":
        return "[Deprecated] Hooks configuration moved to settings.json. See /config for setup."

    logger.info(f"[Command] Unknown slash command: {command}")
    return None


# ===== 辅助函数：生成 messages 摘要 =====
def _summarize_messages(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        item = {"role": m["role"]}
        content = m.get("content") or ""
        if content:
            item["content"] = content  # 记录完整 content
        if m.get("tool_calls"):
            item["tool_calls"] = [
                {"name": tc["function"]["name"], "id": tc["id"]}
                for tc in m["tool_calls"]
            ]
        if m.get("tool_call_id"):
            item["tool_call_id"] = m["tool_call_id"]
        out.append(item)
    return out


async def _handle_non_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    start_time = time.time()

    # Helper to push canvas progress
    async def _push_canvas_progress(content: str, action: str = "append") -> None:
        if not _canvas_manager or not session_id:
            return
        try:
            await _canvas_manager.push_update(
                session_id=session_id,
                content=content,
                mode="markdown",
                section="main",
                action=action,
            )
        except Exception:
            pass

    # Use unified registry (local + MCP) or default
    registry = _unified_registry or UnifiedToolRegistry(get_default_registry())
    user_tools = payload.get("tools")
    tools = user_tools if user_tools is not None else registry.list_tools()

    # ===== LOG: 初始状态 =====
    logger.info("=" * 80)
    logger.info(f"[REQUEST] session_id={session_id}, model={model}")

    # 记录可用工具（区分来源）
    mcp_tools = []
    builtin_tools = []
    for t in tools:
        name = t['function']['name']
        # MCP 工具名格式: mcp__server__tool
        if name.startswith("mcp__"):
            mcp_tools.append(name)
        else:
            builtin_tools.append(name)
    logger.info(f"[TOOLS] builtin={builtin_tools}, mcp={mcp_tools}")
    logger.debug(f"[TOOLS DETAIL] {json.dumps(tools, ensure_ascii=False, indent=2)}")

    # Build messages: session history + current request messages
    new_messages = list(payload.get("messages", []))
    if session_id:
        session = _session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Use memory management to limit context window
        max_tokens = session.context_window or 64000
        history = _session_manager.get_messages_with_limit(session_id, max_tokens)
        messages = history + new_messages

        # ===== LOG: Session 状态 =====
        logger.info(f"[SESSION] skills={session.skills}, system_prompt={session.system_prompt[:100] if session.system_prompt else None}...")
        logger.info(f"[SESSION] context_window={session.context_window}, history_count={len(history)}")

        # Build system prompt using core module (task-based memory retrieval)
        if _prompt_builder:
            system_prompt = _prompt_builder.build(
                messages=messages,
                goal=None,  # TODO: session.goal if available
                session_system_prompt=session.system_prompt,
            )
            if system_prompt:
                messages = _prompt_builder.insert_into_messages(messages, system_prompt)
                logger.info(f"[SYSTEM PROMPT] length={len(system_prompt)}")
                logger.debug(f"[SYSTEM PROMPT FULL]:\n{system_prompt}")
    else:
        messages = list(new_messages)
        logger.info("no session_id, using payload messages directly")

    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools")}

    # ===== Clean orphan tool messages =====
    messages = clean_orphan_tool_messages(messages)

    # ===== LOG: 最终发给 LLM 的 messages =====
    logger.info(f"[MESSAGES] count={len(messages)}")
    logger.debug(f"[MESSAGES FULL]:\n{json.dumps(messages, ensure_ascii=False, indent=2)}")

    # 记录用户输入到 chat.log
    for m in new_messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            chat_logger.info(f"[USER] session={session_id}: {content[:200]}")

    # ===== Slash command processing (/goal, etc.) =====
    # Check if any new message is a slash command
    for m in new_messages:
        if m.get("role") == "user":
            cmd_result = _process_slash_command(m.get("content", ""))
            if cmd_result is not None:
                logger.info(f"[COMMAND] Slash command processed: {cmd_result[:100]}")
                return {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": cmd_result},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }

    # Save incoming messages to session
    if session_id:
        for msg in new_messages:
            _session_manager.add_message(
                session_id=session_id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                tool_call_id=msg.get("tool_call_id"),
                name=msg.get("name"),
            )
        saved_count = len(messages)
        logger.info(f"saved_count={saved_count} (messages persisted to session)")

    with mlflow.start_run(run_name=f"gateway-{model}", nested=True):
        mlflow.log_param("model", model)
        mlflow.log_param("runtime", "openai")
        mlflow.log_param("llm_base_url", LLM_BASE_URL)
        mlflow.log_param("temperature", payload.get("temperature"))
        mlflow.log_param("client_host", request.client.host if request.client else "unknown")
        mlflow.log_param("path", "/v1/chat/completions")
        mlflow.log_param("tools_available", len(tools))

        mlflow.log_dict(payload, "request.json")

        # Parent span for the whole request
        with mlflow.start_span(name="chat_completion_request", span_type=SpanType.CHAT_MODEL) as request_span:
            request_span.set_inputs({
                "model": model,
                "messages_count": len(messages),
                "messages_summary": _summarize_messages(messages),
                "metadata": {
                    "tools_count": len(tools),
                    "stream": False,
                },
            })

            # === Tool execution loop ===
            n_turns = 0
            turn_log: list[dict[str, Any]] = []

            while True:
                # ===== Auto-compaction check =====
                if session_id and _compaction_manager and session:
                    calculator = TokenCalculator(model)
                    current_tokens = calculator.count_messages(messages)

                    # Check if compaction needed
                    level = _compaction_manager.check_compaction_needed(
                        session_id=session_id,
                        current_tokens=current_tokens,
                        context_window=session.context_window or 64000,
                    )

                    if level:
                        logger.info(f"[COMPACTION] Triggering level {level} for session {session_id}")
                        # Calculate target tokens (40% of context window)
                        target_tokens = int((session.context_window or 64000) * 0.4)
                        messages = await _compaction_manager.compact(
                            session_id=session_id,
                            messages=messages,
                            level=level,
                            calculator=calculator,
                            target_tokens=target_tokens,
                        )
                        # Log new token count
                        new_tokens = calculator.count_messages(messages)
                        logger.info(f"[COMPACTION] New token count: {new_tokens}")

                # ===== Token Budget check =====
                # Check budget and decide whether to continue
                # Budget can be set via session metadata or defaults to 50000
                if session_id and _budget_manager:
                    # Get budget from session or use default
                    session_budget = getattr(session, 'token_budget', None) if session else None
                    budget = session_budget or 50000  # Default budget

                    # Estimate current tokens (use calculator if available, or simple estimate)
                    if 'calculator' in dir() and calculator:
                        current_tokens = calculator.count_messages(messages)
                    else:
                        current_tokens = estimate_tokens_simple(messages)

                    # Check budget decision
                    decision = _budget_manager.check_budget(
                        session_id=session_id,
                        budget=budget,
                        current_tokens=current_tokens,
                    )

                    # Handle stop decision
                    if not decision.should_continue and hasattr(decision, 'completion_event'):
                        logger.info(
                            f"[BUDGET] Budget limit reached for session {session_id}: "
                            f"tokens={current_tokens}, budget={budget}"
                        )
                        # Generate budget report message
                        from sessions.budget import generate_budget_report
                        report = generate_budget_report(decision.completion_event)
                        # Inject budget report as final response
                        messages.append({
                            "role": "assistant",
                            "content": f"[Budget Limit Reached]\n\n{report}",
                        })
                        break  # Exit the tool loop

                    # Handle continue with nudge
                    if decision.should_continue and hasattr(decision, 'nudge_message') and decision.nudge_message:
                        # Inject nudge message to guide agent efficiency
                        logger.info(f"[BUDGET] Progress: {decision.pct}% of budget used")

                call_kwargs: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
                if tools:
                    call_kwargs["tools"] = tools

                # 记录发给 LLM 的完整请求
                logger.info(f"[LLM REQUEST] model={model}, messages_count={len(messages)}, tools_count={len(tools) if tools else 0}")
                logger.debug(f"[LLM REQUEST FULL]:\n{json.dumps(call_kwargs, ensure_ascii=False, indent=2)}")

                # ===== LLM CALL (带轮次序号 + messages 摘要) =====
                with mlflow.start_span(
                    name=f"Completions (turn {n_turns})",
                    span_type=SpanType.CHAT_MODEL,
                ) as llm_span:
                    llm_span.set_inputs({
                        "turn": n_turns,
                        "model": model,
                        "messages_count": len(messages),
                        "messages_summary": _summarize_messages(messages),
                        **kwargs,
                    })
                    # Push canvas progress: LLM thinking
                    await _push_canvas_progress(f"🤔 正在思考 (第 {n_turns + 1} 轮)...")

                    # LLM call with error recovery (retry network/rate-limit/timeout)
                    result = None
                    llm_error = None
                    for attempt in range(3):
                        try:
                            async with _llm_semaphore:
                                # Use ProviderRegistry if available (with fallback)
                                if _provider_registry and _provider_registry.get_fallback_chain():
                                    result = await _provider_registry.complete_with_fallback(
                                        messages=messages,
                                        model=model,
                                        tools=tools if tools else None,
                                        **kwargs
                                    )
                                else:
                                    # Fallback to direct client
                                    response = await asyncio.to_thread(
                                        llm_client.chat.completions.create, **call_kwargs
                                    )
                                    result = response.model_dump()
                            break  # Success — exit retry loop
                        except Exception as e:
                            llm_error = e
                            error_kind = classify_error(e)
                            strategy = get_retry_config(error_kind)

                            # Auth errors: fail immediately
                            if error_kind == ErrorKind.AUTH:
                                logger.error(f"[RECOVERY] Auth error, not retrying: {e}")
                                break

                            # Non-retryable: fail
                            if error_kind == ErrorKind.UNKNOWN or attempt >= strategy.max_retries:
                                logger.error(f"[RECOVERY] {error_kind.value}: {e} (attempt {attempt + 1})")
                                break

                            delay = calculate_delay(attempt, strategy)
                            logger.warning(
                                f"[RECOVERY] {error_kind.value}: {e}. "
                                f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{strategy.max_retries})"
                            )
                            await asyncio.sleep(delay)

                    if result is None:
                        llm_span.set_outputs({
                            "error": str(llm_error),
                            "error_type": type(llm_error).__name__ if llm_error else "unknown",
                        })
                        request_span.set_outputs({
                            "error": str(llm_error),
                            "error_type": type(llm_error).__name__ if llm_error else "unknown",
                            "latency_seconds": time.time() - start_time,
                        })
                        logger.error(f"LLM API error after retries: {llm_error}")
                        raise HTTPException(
                            status_code=502,
                            detail={"error": {"message": str(llm_error), "type": type(llm_error).__name__ if llm_error else "unknown"}},
                        )

                    llm_span.set_outputs({
                        "finish_reason": result["choices"][0].get("finish_reason"),
                        "has_tool_calls": bool(result["choices"][0]["message"].get("tool_calls")),
                    })

                choice = result["choices"][0]
                message = choice["message"]
                messages.append(message)

                # ===== LOG: LLM 返回 =====
                content_preview = (message.get("content") or "")[:70].replace("\n", "\\n")
                finish_reason = choice.get("finish_reason")
                logger.info(f"LLM response content_preview: '{content_preview}...'")
                logger.info(f"LLM finish_reason: {finish_reason}")

                tool_calls = message.get("tool_calls")
                if not tool_calls:
                    logger.info("[RESPONSE] no tool_calls, done")
                    break

                n_turns += 1
                logger.info(f"[TOOL CALL] turn={n_turns}, tools={[tc['function']['name'] for tc in tool_calls]}")

                if n_turns > 50:
                    logger.warning("[TOOL LIMIT] exceeded 10 turns, forcing break")
                    for tc in tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "Tool execution limit reached (10). Please provide your best answer based on available information.",
                        })
                    break

                turn_log.append({
                    "llm_response": result,
                    "tool_results": [],
                })

                # ===== TOOL EXECUTION =====
                with mlflow.start_span(
                    name=f"Tool Execution (turn {n_turns})",
                    span_type=SpanType.CHAIN,
                ) as tool_span:
                    tool_calls_summary = [
                        {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                        for tc in tool_calls
                    ]
                    tool_span.set_inputs({
                        "turn": n_turns,
                        "tool_calls": tool_calls_summary,
                    })

                    # Create ToolExecutor
                    executor = ToolExecutor(
                        registry=registry,
                        session_id=session_id,
                        canvas_manager=_canvas_manager,
                    )

                    # Execute all tools
                    logger.info(f"[TOOL] {[tc['function']['name'] for tc in tool_calls]}")
                    results = await executor.execute_tools(tool_calls)

                    # Process results and append to messages
                    skill_injections: list[str] = []
                    for tc in tool_calls:
                        tc_id = tc["id"]
                        fn_name = tc["function"]["name"]
                        tool_result = results.get(tc_id)

                        if tool_result is None:
                            tool_result_str = f"Error: Tool {fn_name} not executed"
                        elif tool_result.error:
                            tool_result_str = tool_result.error
                        else:
                            tool_result_str = tool_result.content

                        logger.info(f"[TOOL RESULT] {fn_name}: length={len(tool_result_str)}")
                        logger.debug(f"[TOOL RESULT FULL]: {tool_result_str}")

                        # Handle Skill tool specially - inject skill instructions
                        if fn_name == "Skill" and not tool_result.error:
                            try:
                                skill_data = json.loads(tool_result_str)
                                if skill_data.get("success") and skill_data.get("skill_instructions"):
                                    skill_name = skill_data.get("skill_name")
                                    skill_desc = skill_data.get("skill_description")
                                    skill_instructions = skill_data.get("skill_instructions")
                                    skill_tools_list = skill_data.get("skill_tools", [])

                                    # Build skill content message
                                    skill_content = f"<skill>\nSkill '{skill_name}' loaded.\n\nDescription: {skill_desc}\n\nInstructions:\n{skill_instructions}\n"

                                    if skill_tools_list:
                                        skill_content += f"\nTools available in this skill:\n"
                                        for t in skill_tools_list:
                                            skill_content += f"- {t}\n"

                                    skill_content += "</skill>"
                                    skill_injections.append(skill_content)
                                    logger.info(f"[SKILL LOADED] {skill_name}, instructions_length={len(skill_instructions)}")

                                    # Change tool_result to a simpler success message
                                    tool_result_str = f"Successfully loaded skill '{skill_name}'"
                            except json.JSONDecodeError:
                                pass

                        # Log tool execution details
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            fn_args = {}

                        turn_log[-1]["tool_results"].append({
                            "name": fn_name,
                            "arguments": fn_args,
                            "result": tool_result_str,
                            "duration_ms": tool_result.duration_ms if tool_result else 0,
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": tool_result_str,
                        })

                    # Inject all skill instructions as assistant messages
                    for skill_content in skill_injections:
                        messages.append({
                            "role": "assistant",
                            "content": skill_content,
                        })
                        logger.info(f"[SKILL INJECTION] added assistant message with skill instructions")

                    tool_span.set_outputs({
                        "executed_count": len(tool_calls),
                        "tool_names": [tc["function"]["name"] for tc in tool_calls],
                        "full_results": [tr["result"] for tr in turn_log[-1]["tool_results"]],
                        "parallel_execution": True,
                        "safe_tools": [tc["function"]["name"] for tc in tool_calls if is_safe(tc["function"]["name"])],
                        "unsafe_tools": [tc["function"]["name"] for tc in tool_calls if not is_safe(tc["function"]["name"])],
                    })

            latency = time.time() - start_time
            mlflow.log_metric("latency_seconds", latency)
            mlflow.log_metric("tool_loop_turns", n_turns)

            mlflow.log_dict(result, "response.json")
            mlflow.log_dict({
                "tool_loop_turns": n_turns,
                "full_messages": messages,
                "turn_log": turn_log,
            }, "conversation.json")

            _log_mlflow_artifacts(result)

            # ===== request_span outputs: 去重 + 摘要 =====
            request_span.set_outputs({
                "latency_seconds": latency,
                "tool_loop_turns": n_turns,
                "total_messages": len(messages),
                "final_content": result["choices"][0]["message"].get("content", "")[:100],
                "conversation_artifact": "conversation.json",
                "turn_log_summary": [
                    {
                        "turn": i + 1,
                        "tools": [tr["name"] for tr in turn["tool_results"]],
                        "tool_count": len(turn["tool_results"]),
                    }
                    for i, turn in enumerate(turn_log)
                ] if turn_log else "no tool execution",
                "final_messages_summary": _summarize_messages(messages),
            })

            # Export trace to file system
            trace_id = request_span.request_id
            _export_trace_to_filesystem(trace_id, 4)

            # Persist new messages (assistant + tool) to session
            if session_id:
                new_msg_count = 0
                for msg in messages[saved_count:]:
                    _session_manager.add_message(
                        session_id=session_id,
                        role=msg["role"],
                        content=msg.get("content", ""),
                        tool_calls=json.dumps(msg["tool_calls"]) if msg.get("tool_calls") else None,
                        tool_call_id=msg.get("tool_call_id"),
                        name=msg.get("name"),
                    )
                    new_msg_count += 1
                logger.info(f"[PERSIST] {new_msg_count} messages saved to session")

            # 记录 assistant 响应到 chat.log
            assistant_content = result["choices"][0]["message"].get("content", "")
            if assistant_content:
                chat_logger.info(f"[ASSISTANT] session={session_id}: {assistant_content[:500]}")

            logger.info(f"[REQUEST END] latency={latency:.3f}s, turns={n_turns}")
            logger.info("=" * 80)

            # Push canvas progress: completed
            await _push_canvas_progress(f"\n✅ 回答完成 (耗时 {latency:.1f}s)")

        return result


def _log_mlflow_artifacts(result: dict[str, Any]) -> None:
    try:
        message = result["choices"][0]["message"]
        answer = message.get("content", "")
        reasoning = message.get("reasoning", "")
        mlflow.log_text(answer or "", "answer.txt")
        if reasoning:
            mlflow.log_text(reasoning, "reasoning.txt")
    except Exception:
        pass


def _export_trace_to_filesystem(trace_id: str, experiment_id: int) -> None:
    """Export trace data to file system as traces.json artifact."""
    try:
        from mlflow.tracing.client import TracingClient

        client = TracingClient()
        trace = client.get_trace(trace_id)

        artifact_dir = f"mlruns/{experiment_id}/traces/{trace_id}/artifacts"
        os.makedirs(artifact_dir, exist_ok=True)

        spans_data = {"spans": []}
        for span in trace.data.spans:
            span_dict = {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_id,
                "name": span.name,
                "start_time_unix_nano": span.start_time_ns,
                "end_time_unix_nano": span.end_time_ns,
                "events": span.events or [],
                "status": {"code": "STATUS_CODE_OK", "message": ""},
                "attributes": span.attributes or {},
            }
            spans_data["spans"].append(span_dict)

        with open(f"{artifact_dir}/traces.json", "w") as f:
            json.dump(spans_data, f, ensure_ascii=False)
    except Exception:
        pass