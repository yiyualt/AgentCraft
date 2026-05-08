import json
import os
import time
from typing import Any, Generator

import httpx
import mlflow
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mlflow.entities import SpanType
from openai import OpenAI

from tools import get_default_registry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools

# ===== Config =====
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "ollama-gateway-qwen3-8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()

    model = payload.get("model", "qwen3:8b")
    stream = payload.get("stream", False)

    if stream:
        return _handle_streaming(request, client, payload, model)
    else:
        return _handle_non_streaming(request, client, payload, model)


def _handle_non_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    start_time = time.time()

    registry = get_default_registry()
    user_tools = payload.get("tools")
    tools = user_tools if user_tools else registry.list_tools()

    # Build messages list from payload
    messages = list(payload.get("messages", []))
    kwargs = {k: v for k, v in payload.items() if k not in ("messages", "tools")}

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
                        response = llm_client.chat.completions.create(**call_kwargs)
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
                    tool_result = registry.dispatch(fn_name, fn_args)
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

        return result


def _handle_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
) -> StreamingResponse:
    """Proxy streaming response from LLM to client while recording to MLflow."""

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

    def generate() -> Generator[str, None, None]:
        collected_content: list[str] = []
        collected_reasoning: list[str] = []
        first_chunk_time = time.time()

        try:
            stream = llm_client.chat.completions.create(
                **inner_kwargs, stream=True
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