import json
import os
import time
from typing import Any

import httpx
import mlflow
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from mlflow.entities import SpanType
from openai import OpenAI

from tools import get_default_registry, UnifiedToolRegistry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools
from tools.mcp import MCPToolManager, MCPConfig
from sessions import SessionManager
from skills import SkillLoader, default_skill_dirs

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

# ===== Logging (写入文件) =====
import logging

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "gateway.log")

logger = logging.getLogger("gateway")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize MCP servers on startup, shut down on exit."""
    global _mcp_manager, _unified_registry

    _app.state.session_manager = _session_manager
    _skill_loader.load()
    _app.state.skill_loader = _skill_loader

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

    yield

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


# ===== 辅助函数：生成 messages 摘要（不存完整内容） =====
def _summarize_messages(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        item = {"role": m["role"]}
        content = m.get("content") or ""
        if content:
            item["content_preview"] = content[:80].replace("\n", "\\n")
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
    logger.info("=" * 60)
    logger.info(f"[TURN START] session_id={session_id}, model={model}")
    logger.info(f"user_tools is None: {user_tools is None}")
    logger.info(f"tools count: {len(tools)}")
    logger.info(f"tool names: {[t['function']['name'] for t in tools]}")

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
        logger.info(f"session.skills={session.skills}")
        logger.info(f"session.system_prompt={session.system_prompt}")
        logger.info(f"session.context_window={session.context_window}")
        logger.info(f"history messages count: {len(history)} (truncated)")

        # Build system prompt from session system_prompt + enabled skills
        system_parts = []
        if session.system_prompt:
            system_parts.append(session.system_prompt)
            logger.info("added session.system_prompt to system_parts")

        if session.skills:
            skill_names = [n.strip() for n in session.skills.split(",") if n.strip()]
            logger.info(f"parsed skill_names: {skill_names}")

            skill_prompt = _skill_loader.build_prompt(skill_names)
            logger.info(f"skill_prompt length: {len(skill_prompt) if skill_prompt else 0}")
            if skill_prompt:
                logger.debug(f"skill_prompt content:\n{skill_prompt}")
                system_parts.append(skill_prompt)

        if system_parts:
            logger.info(f"system_parts count: {len(system_parts)}")
            for i, part in enumerate(system_parts):
                preview = part[:80].replace("\n", "\\n")
                logger.info(f"  system_parts[{i}] preview: '{preview}...'")
        else:
            logger.info("system_parts is empty")

        if system_parts and not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
            logger.info("inserted system message at messages[0]")
    else:
        messages = list(new_messages)
        logger.info("no session_id, using payload messages directly")

    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools")}

    # ===== LOG: 最终发给 LLM 的 messages =====
    logger.info(f"final messages count: {len(messages)}")
    for i, m in enumerate(messages):
        content = m.get("content", "") or ""
        preview = content[:70].replace("\n", "\\n")
        role = m["role"]
        extra = ""
        if role == "tool":
            extra = f" tool_call_id={m.get('tool_call_id')}"
        elif role == "assistant" and m.get("tool_calls"):
            extra = f" tool_calls_count={len(m['tool_calls'])}"
        logger.info(f"  messages[{i}] role={role}{extra}, content_preview='{preview}...'")

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
                call_kwargs: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
                if tools:
                    call_kwargs["tools"] = tools

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
                    try:
                        async with _llm_semaphore:
                            response = await asyncio.to_thread(
                                llm_client.chat.completions.create, **call_kwargs
                            )
                    except Exception as e:
                        llm_span.set_outputs({
                            "error": str(e),
                            "error_type": type(e).__name__,
                        })
                        request_span.set_outputs({
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "latency_seconds": time.time() - start_time,
                        })
                        logger.error(f"LLM API error: {type(e).__name__}: {e}")
                        raise HTTPException(
                            status_code=502,
                            detail={"error": {"message": str(e), "type": type(e).__name__}},
                        )
                    result = response.model_dump()
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
                    logger.info("no tool_calls → breaking loop")
                    break

                n_turns += 1
                logger.info(f"tool_calls detected, count={len(tool_calls)}, n_turns={n_turns}")

                if n_turns > 10:
                    logger.warning("tool loop exceeded 10 turns, forcing break")
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
                        logger.info(f"  -> dispatching tool: {fn_name}({json.dumps(fn_args, ensure_ascii=False)})")

                        tool_result = await registry.dispatch(fn_name, fn_args)
                        result_preview = str(tool_result)[:70].replace("\n", "\\n")
                        logger.info(f"  <- tool_result preview: '{result_preview}...'")

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

                    tool_span.set_outputs({
                        "executed_count": len(tool_calls),
                        "tool_names": [tc["function"]["name"] for tc in tool_calls],
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
                logger.info(f"persisted {new_msg_count} new messages to session")

            logger.info(f"[TURN END] latency={latency:.3f}s, tool_loop_turns={n_turns}")
            logger.info("=" * 60)

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