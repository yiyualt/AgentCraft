import json
import os
import time
from typing import Any, Generator

import httpx
import mlflow
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI

# ===== Config =====
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "ollama-gateway-qwen3-8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

# ===== MLflow =====
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(MLFLOW_EXPERIMENT)
mlflow.openai.autolog()

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

    with mlflow.start_run(run_name=f"gateway-{model}"):
        mlflow.log_param("model", model)
        mlflow.log_param("runtime", "ollama")
        mlflow.log_param("ollama_base_url", OLLAMA_BASE_URL)
        mlflow.log_param("temperature", payload.get("temperature"))
        mlflow.log_param("client_host", request.client.host if request.client else "unknown")
        mlflow.log_param("path", "/v1/chat/completions")

        mlflow.log_dict(payload, "request.json")

        response = llm_client.chat.completions.create(**payload)

        latency = time.time() - start_time
        mlflow.log_metric("latency_seconds", latency)

        result = response.model_dump()
        mlflow.log_dict(result, "response.json")

        _log_mlflow_artifacts(result)

        return result


def _handle_streaming(
    request: Request,
    llm_client: OpenAI,
    payload: dict[str, Any],
    model: str,
) -> StreamingResponse:
    """Proxy streaming response from LLM to client while recording to MLflow."""

    stream_payload = {**payload, "stream": True}
    # Don't pass stream in the inner payload since we set it on the SDK call
    inner_kwargs = {k: v for k, v in stream_payload.items() if k != "stream"}

    def generate() -> Generator[str, None, None]:
        collected_content: list[str] = []
        collected_reasoning: list[str] = []
        first_chunk_time = time.time()

        # We record MLflow at the end — the streaming run wrapper below
        # is a separate closure for the non-MLflow chunk stream.
        try:
            stream = llm_client.chat.completions.create(
                **inner_kwargs, stream=True
            )
            for chunk in stream:
                chunk_dict = chunk.model_dump()
                yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"

                # Collect content for MLflow logging
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

        # Log to MLflow after stream completes
        full_answer = "".join(collected_content)
        full_reasoning = "".join(collected_reasoning)

        # We need to capture the run inside the generator but MLflow
        # requires us to start/end outside or use a separate thread
        # -- simplest approach: log synchronously at the end
        import threading
        threading.Thread(
            target=_log_stream_mlflow,
            args=(model, payload, inner_kwargs, time.time() - first_chunk_time,
                  full_answer, full_reasoning, request),
            daemon=True,
        ).start()

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


def _log_stream_mlflow(
    model: str,
    original_payload: dict[str, Any],
    inner_kwargs: dict[str, Any],
    latency: float,
    answer: str,
    reasoning: str,
    request: Request,
) -> None:
    """Log streaming result to MLflow in a background thread."""
    try:
        with mlflow.start_run(run_name=f"gateway-{model}"):
            mlflow.log_param("model", model)
            mlflow.log_param("runtime", "ollama")
            mlflow.log_param("ollama_base_url", OLLAMA_BASE_URL)
            mlflow.log_param("temperature", original_payload.get("temperature"))
            mlflow.log_param("client_host", request.client.host if request.client else "unknown")
            mlflow.log_param("path", "/v1/chat/completions")
            mlflow.log_param("stream", True)

            mlflow.log_dict(original_payload, "request.json")
            mlflow.log_metric("latency_seconds", latency)

            full_result = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                        "reasoning": reasoning or None,
                    },
                }],
            }
            mlflow.log_dict(full_result, "response.json")
            mlflow.log_text(answer or "", "answer.txt")
            if reasoning:
                mlflow.log_text(reasoning, "reasoning.txt")
    except Exception:
        pass