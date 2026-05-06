import os
import time
from typing import Any

import httpx
import mlflow
from fastapi import FastAPI, Request
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
async def chat_completions(request: Request) -> dict[str, Any]:
    payload = await request.json()

    model = payload.get("model", "qwen3:8b")
    temperature = payload.get("temperature")
    stream = payload.get("stream", False)

    if stream:
        return {
            "error": {
                "message": "stream=true is not supported by this gateway yet. Please use stream=false.",
                "type": "unsupported_streaming",
            }
        }

    start_time = time.time()

    with mlflow.start_run(run_name=f"gateway-{model}"):
        mlflow.log_param("model", model)
        mlflow.log_param("runtime", "ollama")
        mlflow.log_param("ollama_base_url", OLLAMA_BASE_URL)
        mlflow.log_param("temperature", temperature)
        mlflow.log_param("client_host", request.client.host if request.client else "unknown")
        mlflow.log_param("path", "/v1/chat/completions")

        mlflow.log_dict(payload, "request.json")

        response = client.chat.completions.create(**payload)

        latency = time.time() - start_time
        mlflow.log_metric("latency_seconds", latency)

        result = response.model_dump()
        mlflow.log_dict(result, "response.json")

        try:
            message = result["choices"][0]["message"]
            answer = message.get("content", "")
            reasoning = message.get("reasoning", "")

            mlflow.log_text(answer or "", "answer.txt")

            if reasoning:
                mlflow.log_text(reasoning, "reasoning.txt")
        except Exception:
            pass

        return result