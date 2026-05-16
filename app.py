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
from core import LLMRequestQueue, StreamHandler
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
MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_OLLAMA", "100"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# LLM Queue Configuration (new architecture)
LLM_QUEUE_ENABLED = os.getenv("LLM_QUEUE_ENABLED", "true").lower() == "true"
LLM_MAX_CONCURRENT = int(os.getenv("LLM_MAX_CONCURRENT", "100"))
LLM_MAX_QUEUE_SIZE = int(os.getenv("LLM_MAX_QUEUE_SIZE", "100"))
LLM_QUEUE_TIMEOUT = float(os.getenv("LLM_QUEUE_TIMEOUT", "60.0"))
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "300.0"))

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
_rate_limit_buckets: dict[str, list[float]] = {}
_rate_limit_lock = asyncio.Lock()

# ===== LLM Queue (new architecture) =====
_llm_queue: LLMRequestQueue | None = None
_stream_handler: StreamHandler | None = None


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

    # LLM Queue initialization (new concurrent request handling)
    global _llm_queue, _stream_handler
    _llm_queue = LLMRequestQueue(
        max_concurrent=LLM_MAX_CONCURRENT,
        max_queue_size=LLM_MAX_QUEUE_SIZE,
        queue_timeout=LLM_QUEUE_TIMEOUT,
        request_timeout=LLM_REQUEST_TIMEOUT,
    )
    await _llm_queue.start()
    _app.state.llm_queue = _llm_queue
    _stream_handler = StreamHandler(_provider_registry)
    _app.state.stream_handler = _stream_handler
    logger.info(
        f"[LLMQueue] Initialized: max_concurrent={LLM_MAX_CONCURRENT}, "
        f"max_queue={LLM_MAX_QUEUE_SIZE}, queue_timeout={LLM_QUEUE_TIMEOUT}s"
    )

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
    if _llm_queue:
        await _llm_queue.stop()
    if _mcp_manager:
        await _mcp_manager.shutdown()


app = FastAPI(title="Ollama MLflow Gateway", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


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
def list_sessions() -> list[dict[str, Any]]:
    """List all active sessions."""
    sessions = _session_manager.list_sessions()
    return [
        {
            "id": s.id,
            "name": s.name,
            "model": s.model,
            "message_count": s.message_count,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sessions
    ]


@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Get session details."""
    session = _session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.get("/v1/sessions/{session_id}/messages")
def get_session_messages(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get messages for a session."""
    session = _session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = _session_manager.get_messages_openai(session_id, limit)
    return messages


@app.patch("/v1/sessions/{session_id}")
async def update_session(session_id: str, request: Request) -> dict[str, Any]:
    """Update session (e.g., rename)."""
    body = await request.json()
    session = _session_manager.update_session(session_id, **body)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.delete("/v1/sessions/{session_id}")
def delete_session_endpoint(session_id: str) -> dict[str, str]:
    """Delete a session and its messages."""
    if _session_manager.delete_session(session_id):
        return {"deleted": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/v1/skills")
def list_skills() -> list[dict[str, Any]]:
    return [s.to_dict() for s in _skill_loader.list_skills()]


@app.get("/v1/tools")
def list_tools() -> list[dict[str, Any]]:
    """Return available tools for LLM to use."""
    if _unified_registry is None:
        return []
    return _unified_registry.list_tools()


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

    # Use LLMQueue for concurrent request handling (no direct rejection)
    if _llm_queue is None:
        raise HTTPException(status_code=500, detail="LLM queue not initialized")

    return StreamingResponse(
        _handle_streaming_via_queue(payload, model, session_id),
        media_type="text/event-stream",
    )


@app.get("/llm/queue/status")
def get_llm_queue_status() -> dict[str, Any]:
    """Get LLM request queue status for monitoring."""
    if _llm_queue is None:
        raise HTTPException(status_code=500, detail="LLM queue not initialized")
    return _llm_queue.get_status()


async def _handle_streaming_via_queue(
    payload: dict[str, Any],
    model: str,
    session_id: str | None = None,
):
    """SSE streaming response with tool loop support.

    Architecture:
        Request → Semaphore → Tool Loop (LLM → Tools → LLM ...) → SSE Events

    Uses existing components:
    - ToolExecutor: executes tools with concurrency control
    - clean_orphan_tool_messages: ensures valid tool message chains
    - ProviderRegistry: async streaming LLM calls
    """
    from core.executor import ToolExecutor

    # Build messages from session history + new messages
    new_messages = list(payload.get("messages", []))
    if session_id:
        session = _session_manager.get_session(session_id)
        if session:
            max_tokens = session.context_window or 64000
            history = _session_manager.get_messages_with_limit(session_id, max_tokens)
            messages = history + new_messages
            if _prompt_builder:
                system_prompt = _prompt_builder.build(
                    messages=messages,
                    goal=None,
                    session_system_prompt=session.system_prompt,
                )
                if system_prompt:
                    messages = _prompt_builder.insert_into_messages(messages, system_prompt)
        else:
            messages = new_messages
    else:
        messages = new_messages

    # Clean orphan tool messages before starting
    messages = clean_orphan_tool_messages(messages)

    # Build kwargs (exclude already-handled params)
    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools", "stream", "model")}
    if payload.get("tools"):
        kwargs["tools"] = payload["tools"]

    # Yield queue status event
    yield f"event: queue_status\ndata: {{\"status\": \"waiting\", \"model\": \"{model}\"}}\n\n"

    # Save incoming user messages to session
    if session_id:
        for msg in new_messages:
            _session_manager.add_message(
                session_id=session_id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
            )

    # Create ToolExecutor once (reused across tool turns)
    executor = ToolExecutor(
        registry=_unified_registry,
        session_id=session_id,
        canvas_manager=_canvas_manager,
    )

    # Acquire semaphore (wait in queue)
    async with _llm_queue._semaphore:
        yield f"event: stream_request_start\ndata: {{\"model\": \"{model}\"}}\n\n"

        full_content = ""  # Accumulates all turns for final save
        n_tool_turns = 0

        try:
            # Tool loop: LLM call → execute tools → next LLM call
            while True:
                # Get async stream iterator from ProviderRegistry
                stream = await _provider_registry.stream_iterator(
                    messages=messages,
                    model=model,
                    stream=True,
                    **kwargs,
                )

                # Accumulators for this turn
                turn_content = ""
                tool_calls_list: list[dict] = []
                finish_reason = None

                # Async iterate over stream chunks
                async for chunk in stream:
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # Stream content to frontend
                    if delta.get("content"):
                        text = delta["content"]
                        turn_content += text
                        full_content += text
                        escaped = text.replace('"', '\\"').replace('\n', '\\n')
                        yield f"data: {{\"text\": \"{escaped}\"}}\n\n"

                    # Accumulate tool calls
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while idx >= len(tool_calls_list):
                                tool_calls_list.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                })
                            if tc.get("id"):
                                tool_calls_list[idx]["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tool_calls_list[idx]["function"]["name"] = fn["name"]
                            if fn.get("arguments"):
                                tool_calls_list[idx]["function"]["arguments"] += fn["arguments"]

                    # Finish reason
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]

                # Check if we need to execute tools
                if not tool_calls_list:
                    # No tool calls - stream complete
                    break

                n_tool_turns += 1
                # Notify frontend about tool execution
                tool_names = [tc["function"]["name"] for tc in tool_calls_list]
                yield f"event: tool_exec\ndata: {{\"tools\": {json.dumps(tool_names)}}}\n\n"
                logger.info(f"[Streaming] Turn {n_tool_turns}: executing {tool_names}")

                # Execute tools using ToolExecutor
                results = await executor.execute_tools(tool_calls_list)

                # Append assistant message with tool_calls
                messages.append({
                    "role": "assistant",
                    "content": turn_content,
                    "tool_calls": tool_calls_list,
                })

                # Append tool results
                for tc in tool_calls_list:
                    tc_id = tc["id"]
                    result = results.get(tc_id)
                    if result:
                        messages.append(result.to_tool_message())
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": "Tool not executed",
                        })

                # Clean orphan tool messages before next turn
                messages = clean_orphan_tool_messages(messages)

            # Stream complete
            yield f"data: {{\"finish_reason\": \"{finish_reason or 'stop'}\"}}\n\n"

        except Exception as e:
            logger.error(f"[Streaming] Error: {e}")
            yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"

    # Save final assistant message to session
    if session_id and full_content:
        _session_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=full_content,
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