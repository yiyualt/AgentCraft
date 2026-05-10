import json
import os
import time
from typing import Any, AsyncGenerator

import httpx
import mlflow
import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from mlflow.entities import SpanType
from openai import OpenAI

from tools import get_default_registry, UnifiedToolRegistry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools
from tools.mcp import MCPToolManager, MCPConfig
from sessions import SessionManager

# ===== Config =====
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "ollama-gateway-qwen3-8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

# Concurrency / Rate Limiting
MAX_CONCURRENT_OLLAMA = int(os.getenv("MAX_CONCURRENT_OLLAMA", "1"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ===== MLflow =====
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(MLFLOW_EXPERIMENT)
# We manage LLM call spans manually instead of relying on autolog.
# autolog's Completions span leaves outputs=null when the API errors,
# which produces broken-looking traces in the UI.
mlflow.openai.autolog(log_traces=False)

# ===== Ollama OpenAI-compatible Client =====
client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
    http_client=httpx.Client(
        trust_env=False,
        timeout=300,
    ),
)

app = FastAPI(title="Ollama MLflow Gateway")

# ===== Concurrency & Rate Limiting =====
_ollama_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OLLAMA)
_rate_limit_buckets: dict[str, list[float]] = {}
_rate_limit_lock = asyncio.Lock()

# ===== MCP Tool Manager =====
_mcp_manager: MCPToolManager | None = None
_unified_registry: UnifiedToolRegistry | None = None

# ===== Session Manager =====
_session_manager = SessionManager()


@app.on_event("startup")
async def startup_event():
    """Initialize MCP servers on startup."""
    global _mcp_manager, _unified_registry

    app.state.session_manager = _session_manager

    config = MCPConfig.load()
    if config.enabled and config.get_enabled_servers():
        _mcp_manager = MCPToolManager()
        await _mcp_manager.initialize(config)
        _unified_registry = UnifiedToolRegistry(
            get_default_registry(), _mcp_manager
        )
        app.state.mcp_manager = _mcp_manager
        app.state.unified_registry = _unified_registry
    else:
        _unified_registry = UnifiedToolRegistry(get_default_registry())
        app.state.unified_registry = _unified_registry


@app.on_event("shutdown")
async def shutdown_event():
    """Stop MCP servers on shutdown."""
    if _mcp_manager:
        await _mcp_manager.shutdown()


async def _check_rate_limit(request: Request) -> None:
    """Raise HTTPException(429) if the client IP has exceeded the rate limit."""
    if not RATE_LIMIT_ENABLED:
        return
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW

    async with _rate_limit_lock:
        timestamps = _rate_limit_buckets.get(client_ip, [])
        # Prune entries outside the window
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
        "ollama_base_url": OLLAMA_BASE_URL,
    }


_OLLAMA_API_URL = OLLAMA_BASE_URL.rstrip("/v1").rstrip("/")  # Strip /v1 suffix if present


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    """List available models from Ollama, converted to OpenAI-compatible format."""
    try:
        resp = httpx.get(f"{_OLLAMA_API_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        tags = resp.json()
    except Exception as e:
        return {
            "error": {"message": str(e), "type": type(e).__name__},
        }

    models = tags.get("models", [])
    return {
        "object": "list",
        "data": [
            {
                "id": m["name"],
                "object": "model",
                "created": int(time.mktime(time.strptime(m["modified_at"].split(".")[0], "%Y-%m-%dT%H:%M:%S"))) if "modified_at" in m and m["modified_at"] else 0,
                "owned_by": "ollama",
            }
            for m in models
        ],
    }


# ===== Session REST Endpoints =====


@app.post("/v1/sessions")
async def create_session(request: Request) -> dict[str, Any]:
    body = await request.json()
    session = _session_manager.create_session(
        name=body.get("name", "Untitled"),
        model=body.get("model", "qwen3:8b"),
        system_prompt=body.get("system_prompt"),
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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Rate limit check (quick, no LLM)
    await _check_rate_limit(request)

    payload = await request.json()
    model = payload.get("model", "qwen3:8b")
    stream = payload.get("stream", False)
    session_id = request.headers.get("X-Session-Id")

    # Fail-fast semaphore check — avoid parsing payload unnecessarily
    # when the semaphore is already saturated.
    if _ollama_semaphore.locked():
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
        return _handle_streaming(request, client, payload, model, session_id)
    else:
        return await _handle_non_streaming(request, client, payload, model, session_id)


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
    tools = user_tools if user_tools else registry.list_tools()

    # Build messages: session history + current request messages
    new_messages = list(payload.get("messages", []))
    if session_id:
        history = _session_manager.get_messages_openai(session_id)
        messages = history + new_messages
    else:
        messages = list(new_messages)
    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools")}

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
        saved_count = len(messages)  # track what's already persisted

    with mlflow.start_run(run_name=f"gateway-{model}"):
        mlflow.log_param("model", model)
        mlflow.log_param("runtime", "ollama")
        mlflow.log_param("ollama_base_url", OLLAMA_BASE_URL)
        mlflow.log_param("temperature", payload.get("temperature"))
        mlflow.log_param("client_host", request.client.host if request.client else "unknown")
        mlflow.log_param("path", "/v1/chat/completions")
        mlflow.log_param("tools_available", len(tools))

        mlflow.log_dict(payload, "request.json")

        # Parent span for the whole request
        with mlflow.start_span(name="chat_completion_request", span_type=SpanType.CHAT_MODEL) as request_span:
            request_span.set_inputs({
                "model": model,
                "messages": list(messages),
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

                with mlflow.start_span(name="Completions", span_type=SpanType.CHAT_MODEL) as llm_span:
                    llm_span.set_inputs({
                        "model": model,
                        "messages": list(messages),
                        **kwargs,
                    })
                    try:
                        async with _ollama_semaphore:
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
                        return {"error": {"message": str(e), "type": type(e).__name__}}
                    result = response.model_dump()
                    llm_span.set_outputs(result)

                choice = result["choices"][0]
                message = choice["message"]
                messages.append(message)

                tool_calls = message.get("tool_calls")
                if not tool_calls:
                    break  # pure text answer → done

                n_turns += 1
                if n_turns > 10:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": "limit",
                        "content": "Tool execution limit reached (10). Please provide your best answer.",
                    })
                    break

                turn_log.append({
                    "llm_response": result,
                    "tool_results": [],
                })

                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {}
                    tool_result = await registry.dispatch(fn_name, fn_args)
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

            request_span.set_outputs({
                "latency_seconds": latency,
                "tool_loop_turns": n_turns,
                "messages": list(messages),
                "final_content": result["choices"][0]["message"].get("content", ""),
            })

            # Export trace to file system
            trace_id = request_span.request_id
            _export_trace_to_filesystem(trace_id, 4)

            # Persist new messages (assistant + tool) to session
            if session_id:
                for msg in messages[saved_count:]:
                    _session_manager.add_message(
                        session_id=session_id,
                        role=msg["role"],
                        content=msg.get("content", ""),
                        tool_calls=json.dumps(msg["tool_calls"]) if msg.get("tool_calls") else None,
                        tool_call_id=msg.get("tool_call_id"),
                        name=msg.get("name"),
                    )

        return result


def _handle_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
    session_id: str | None = None,
) -> StreamingResponse:
    """Proxy streaming response from LLM to client while recording to MLflow."""

    # Load session history and save incoming messages
    new_messages = list(payload.get("messages", []))
    if session_id:
        history = _session_manager.get_messages_openai(session_id)
        full_messages = history + new_messages
        for msg in new_messages:
            _session_manager.add_message(
                session_id=session_id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                tool_call_id=msg.get("tool_call_id"),
                name=msg.get("name"),
            )
        payload = {**payload, "messages": full_messages}

    stream_payload = {**payload, "stream": True}
    inner_kwargs = {k: v for k, v in stream_payload.items() if k != "stream"}

    mlflow.start_run(run_name=f"gateway-{model}")
    mlflow.log_param("model", model)
    mlflow.log_param("runtime", "ollama")
    mlflow.log_param("ollama_base_url", OLLAMA_BASE_URL)
    mlflow.log_param("temperature", payload.get("temperature"))
    mlflow.log_param("client_host", request.client.host if request.client else "unknown")
    mlflow.log_param("path", "/v1/chat/completions")
    mlflow.log_param("stream", True)
    mlflow.log_dict(payload, "request.json")

    async def generate() -> AsyncGenerator[str, None]:
        collected_content: list[str] = []
        collected_reasoning: list[str] = []
        first_chunk_time = time.time()

        try:
            async with _ollama_semaphore:
                stream = await asyncio.to_thread(
                    llm_client.chat.completions.create, **inner_kwargs, stream=True
                )
                for chunk in stream:
                    chunk_dict = chunk.model_dump()
                    yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"

                    delta = chunk_dict.get("choices", [{}])[0].get("delta", {})
                    if delta.get("content"):
                        collected_content.append(delta["content"])
                    if delta.get("reasoning"):
                        collected_reasoning.append(delta["reasoning"])

                yield "data: [DONE]\n\n"

        except Exception as e:
            error_body = json.dumps({"error": {"message": str(e), "type": "stream_error"}}, ensure_ascii=False)
            yield f"data: {error_body}\n\n"
            yield "data: [DONE]\n\n"
            return
        finally:
            latency = time.time() - first_chunk_time
            full_answer = "".join(collected_content)
            full_reasoning = "".join(collected_reasoning)

            mlflow.log_metric("latency_seconds", latency)
            full_result = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_answer,
                        "reasoning": full_reasoning or None,
                    },
                }],
            }
            mlflow.log_dict(full_result, "response.json")
            mlflow.log_text(full_answer or "", "answer.txt")
            if full_reasoning:
                mlflow.log_text(full_reasoning, "reasoning.txt")

            if session_id and full_answer:
                _session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_answer,
                )

            mlflow.end_run()

    return StreamingResponse(generate(), media_type="text/event-stream")


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