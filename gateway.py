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
from mlflow.entities import SpanType
from openai import OpenAI

from tools import get_default_registry, UnifiedToolRegistry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools
from tools.canvas_tools import set_canvas_manager  # Canvas tools
from tools.agent_executor import AgentExecutor, set_agent_executor  # Agent executor
from tools.skill_tools import *  # noqa: F401,F403 — register Skill tool
from tools.mcp import MCPToolManager, MCPConfig
from tools.sandbox import SandboxExecutor, SandboxConfig
from sessions import SessionManager, TokenCalculator, CompactionManager, CompactionConfig, BudgetManager, estimate_tokens_simple, ResilientExecutor, classify_error, get_retry_config, calculate_delay, ErrorKind, PermissionMode
from skills import SkillLoader, default_skill_dirs
from channels import ChannelRouter
from channels.telegram import TelegramChannel
from channels.web import WebChannel
from canvas import CanvasManager, CanvasChannel

# ===== Config =====
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "agentcraft-gateway")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-default")

# Concurrency / Rate Limiting
MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_OLLAMA", "1"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# Sandbox Execution
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false").lower() == "true"
SANDBOX_NETWORK = os.getenv("SANDBOX_NETWORK", "false").lower() == "true"  # Enable network
SANDBOX_HOST_BIN = os.getenv("SANDBOX_HOST_BIN", "false").lower() == "true"  # Mount host /usr/bin
SANDBOX_PIP_PACKAGES = os.getenv("SANDBOX_PIP_PACKAGES", "").split(",") if os.getenv("SANDBOX_PIP_PACKAGES") else []
SANDBOX_READ_DIRS = os.getenv("SANDBOX_READ_DIRS", "").split(",") if os.getenv("SANDBOX_READ_DIRS") else []
SANDBOX_WRITE_DIRS = os.getenv("SANDBOX_WRITE_DIRS", "").split(",") if os.getenv("SANDBOX_WRITE_DIRS") else []

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


def _clean_orphan_tool_messages(messages: list[dict]) -> list[dict]:
    """Remove orphan tool messages without preceding tool_calls.

    Tool messages must have a preceding assistant message with tool_calls.
    This ensures messages list is valid for LLM API.
    """
    cleaned = []
    last_assistant_tool_calls = None
    removed_count = 0

    for msg in messages:
        role = msg.get("role")

        if role == "assistant":
            # Track tool_calls from this assistant message
            last_assistant_tool_calls = msg.get("tool_calls")
            cleaned.append(msg)
        elif role == "tool":
            # Check if there's a preceding assistant with tool_calls
            if last_assistant_tool_calls:
                # Verify tool_call_id matches
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    matching_ids = [tc["id"] for tc in last_assistant_tool_calls]
                    if tool_call_id in matching_ids:
                        cleaned.append(msg)
                    else:
                        removed_count += 1
                else:
                    removed_count += 1
            else:
                removed_count += 1
        else:
            # Keep system and user messages
            cleaned.append(msg)
            # Reset tool_calls tracker after user message
            if role == "user":
                last_assistant_tool_calls = None

    if removed_count > 0:
        logger.info(f"[MESSAGES] Cleaned orphan tool messages: removed {removed_count}")

    return cleaned


# ===== MCP Tool Manager =====
_mcp_manager: MCPToolManager | None = None
_unified_registry: UnifiedToolRegistry | None = None

# ===== Session Manager =====
_session_manager = SessionManager()

# ===== Skills =====
_skill_loader = SkillLoader(default_skill_dirs())
_skill_loader.load()
set_skill_loader(_skill_loader)  # Set skill loader for Skill tool

# ===== Sandbox Executor =====
_sandbox_executor: SandboxExecutor | None = None

# ===== Canvas =====
_canvas_manager: CanvasManager | None = None
_canvas_channel: CanvasChannel | None = None

# ===== Compaction =====
_compaction_manager: CompactionManager | None = None

# ===== Budget =====
_budget_manager: BudgetManager | None = None

# ===== Error Recovery =====
_recovery_executor: ResilientExecutor | None = None

# ===== Channels =====
_channel_router = ChannelRouter()
_telegram_channel: TelegramChannel | None = None
_web_channel: WebChannel | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize MCP servers and channels on startup, shut down on exit."""
    global _mcp_manager, _unified_registry, _telegram_channel, _web_channel, _sandbox_executor, _canvas_manager, _canvas_channel

    _app.state.session_manager = _session_manager
    _skill_loader.load()
    _app.state.skill_loader = _skill_loader

    # Canvas initialization (before channels, so tools can use it)
    _canvas_manager = CanvasManager()
    _app.state.canvas_manager = _canvas_manager
    set_canvas_manager(_canvas_manager)
    logger.info("[Canvas] CanvasManager initialized")

    # Sandbox initialization
    if SANDBOX_ENABLED:
        sandbox_config = SandboxConfig(
            network_disabled=not SANDBOX_NETWORK,
            mount_host_bin=SANDBOX_HOST_BIN,
            pip_packages=SANDBOX_PIP_PACKAGES,
            read_dirs=SANDBOX_READ_DIRS,
            write_dirs=SANDBOX_WRITE_DIRS,
        )
        _sandbox_executor = SandboxExecutor(sandbox_config)
        _app.state.sandbox_executor = _sandbox_executor
        logger.info(f"Sandbox executor initialized: network={SANDBOX_NETWORK}, host_bin={SANDBOX_HOST_BIN}, pip={SANDBOX_PIP_PACKAGES}")

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

    # Agent Executor initialization
    agent_executor = AgentExecutor(
        llm_client=client,
        registry=_unified_registry,
        session_manager=_session_manager,
        model="deepseek-chat",
        base_url=LLM_BASE_URL,
    )
    set_agent_executor(agent_executor)
    logger.info("[AgentExecutor] Initialized with unified registry")

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
    agent_executor.set_fork_manager(fork_manager)
    logger.info("[Fork] ForkManager initialized")

    # Initialize channels
    _telegram_channel = TelegramChannel(_session_manager)
    _channel_router.register(_telegram_channel)

    _web_channel = WebChannel(_session_manager)
    _channel_router.register(_web_channel)
    _app.include_router(_web_channel.get_router())

    # Canvas channel (SSE streaming workspace)
    _canvas_channel = CanvasChannel(_canvas_manager)
    _channel_router.register(_canvas_channel)
    _app.include_router(_canvas_channel.get_router())
    logger.info("[Canvas] CanvasChannel registered at /canvas")

    await _channel_router.start_all()

    yield

    # Cleanup
    await _channel_router.stop_all()
    if _sandbox_executor:
        await _sandbox_executor.cleanup()
    if _mcp_manager:
        await _mcp_manager.shutdown()


app = FastAPI(title="Ollama MLflow Gateway", lifespan=lifespan)


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
        "sandbox_enabled": str(SANDBOX_ENABLED),
    }


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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Rate limit check (quick, no LLM)
    await _check_rate_limit(request)

    payload = await request.json()
    model = payload.get("model", "deepseek-chat")
    session_id = request.headers.get("X-Session-Id")

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

    return await _handle_non_streaming(request, client, payload, model, session_id)


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
        executor = get_agent_executor()
        if not executor:
            return "[Error] Agent executor not initialized"
        if args:
            result = executor.set_goal(args)
            logger.info(f"[Goal] Set: {args}")
            return result
        else:
            result = executor.clear_goal()
            logger.info("[Goal] Cleared")
            return result

    if command == "/permission":
        executor = get_agent_executor()
        if not executor:
            return "[Error] Agent executor not initialized"
        if not args:
            mode = executor.get_permission_mode()
            return f"Current permission mode: **{mode.value}**\nAvailable modes: default, acceptEdits, bypass, auto, plan"
        mode_map = {
            "default": PermissionMode.DEFAULT,
            "acceptedits": PermissionMode.ACCEPT_EDITS,
            "accept_edits": PermissionMode.ACCEPT_EDITS,
            "bypass": PermissionMode.BYPASS,
            "auto": PermissionMode.AUTO,
            "plan": PermissionMode.PLAN,
        }
        mode = mode_map.get(args.lower().replace(" ", "_"))
        if mode is None:
            return f"Unknown mode: {args}. Available: {list(mode_map.keys())}"
        executor.set_permission_mode(mode)
        return f"Permission mode set to: **{mode.value}**"

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

        # Build system prompt from session system_prompt + skill listing
        system_parts = []
        if session.system_prompt:
            system_parts.append(session.system_prompt)

        # Inject skill listing (Claude Code style - all available skills)
        # The model will decide which skill to invoke via Skill tool
        skill_listing = _skill_loader.build_skill_listing()
        if skill_listing:
            logger.info(f"[SKILLS] listing_length={len(skill_listing)}")
            logger.debug(f"[SKILLS LISTING]:\n{skill_listing}")
            system_parts.append(skill_listing)

        if system_parts:
            full_system_prompt = "\n\n".join(system_parts)
            logger.info(f"[SYSTEM PROMPT] length={len(full_system_prompt)}")
            logger.debug(f"[SYSTEM PROMPT FULL]:\n{full_system_prompt}")

        if system_parts and not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
            logger.info("inserted system message at messages[0]")
    else:
        messages = list(new_messages)
        logger.info("no session_id, using payload messages directly")

    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools")}

    # ===== Clean orphan tool messages =====
    messages = _clean_orphan_tool_messages(messages)

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

    with mlflow.start_run(run_name=f"gateway-{model}"):
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
                    # LLM call with error recovery (retry network/rate-limit/timeout)
                    result = None
                    llm_error = None
                    for attempt in range(3):
                        try:
                            async with _llm_semaphore:
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

                if n_turns > 10:
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

                # ===== TOOL EXECUTION (独立 span) =====
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

                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            fn_args = {}
                        logger.info(f"[TOOL EXEC] {fn_name}({json.dumps(fn_args, ensure_ascii=False)})")
                        logger.debug(f"[TOOL ARGS FULL]: {json.dumps(fn_args, ensure_ascii=False, indent=2)}")

                        # Set session_id context for canvas tools
                        if _canvas_manager:
                            from canvas import set_current_session_id
                            set_current_session_id(session_id)

                        # Execute in sandbox or directly
                        if SANDBOX_ENABLED and _sandbox_executor:
                            # Sandbox execution: get tool source code first
                            tool_code = registry.get_source_code(fn_name)
                            if tool_code is None:
                                # MCP tools cannot be sandboxed, fall back to direct dispatch
                                logger.warning(f"[SANDBOX] {fn_name} has no source code (MCP tool?), falling back to direct dispatch")
                                tool_result = await registry.dispatch(fn_name, fn_args)
                            else:
                                logger.info(f"[SANDBOX] executing {fn_name} in isolated container (code_len={len(tool_code)})")
                                result = await _sandbox_executor.run_tool(fn_name, fn_args, tool_code)
                                tool_result = result.output if result.success else f"Error: {result.error}"
                                if not result.success:
                                    logger.warning(f"[SANDBOX ERROR] {fn_name}: {result.error}")
                        else:
                            # Direct execution via registry
                            tool_result = await registry.dispatch(fn_name, fn_args)

                        # Clear session_id context after execution
                        if _canvas_manager:
                            from canvas import set_current_session_id
                            set_current_session_id(None)

                        logger.info(f"[TOOL RESULT] {fn_name}: length={len(str(tool_result))}")
                        logger.debug(f"[TOOL RESULT FULL]: {tool_result}")

                        # Handle Skill tool specially - inject skill instructions
                        skill_injection = None
                        if fn_name == "Skill":
                            try:
                                skill_data = json.loads(tool_result)
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
                                    skill_injection = skill_content
                                    logger.info(f"[SKILL LOADED] {skill_name}, instructions_length={len(skill_instructions)}")

                                    # Change tool_result to a simpler success message
                                    tool_result = f"Successfully loaded skill '{skill_name}'"
                            except json.JSONDecodeError:
                                pass

                        turn_log[-1]["tool_results"].append({
                            "name": fn_name,
                            "arguments": fn_args,
                            "result": tool_result,
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": tool_result,
                        })

                        # If Skill tool was invoked, inject skill instructions as assistant message
                        if skill_injection:
                            messages.append({
                                "role": "assistant",
                                "content": skill_injection,
                            })
                            logger.info(f"[SKILL INJECTION] added assistant message with skill instructions")

                    tool_span.set_outputs({
                        "executed_count": len(tool_calls),
                        "tool_names": [tc["function"]["name"] for tc in tool_calls],
                        "full_results": [tr["result"] for tr in turn_log[-1]["tool_results"]],
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