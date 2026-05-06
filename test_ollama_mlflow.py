import mlflow
from openai import OpenAI

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("ollama-qwen3-8b-observability-v2")

# 关键：自动记录 OpenAI SDK 调用，因此也能记录 Ollama /v1 调用
mlflow.openai.autolog()

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # 本地 Ollama 不校验，随便填
)

with mlflow.start_run(run_name="qwen3-8b-basic-chat"):
    mlflow.log_param("model", "qwen3:8b")
    mlflow.log_param("runtime", "ollama")
    mlflow.log_param("endpoint", "http://localhost:11434/v1")
    mlflow.log_param("temperature", 0.3)
    mlflow.log_param("num_ctx", 4096)

    response = client.chat.completions.create(
        model="qwen3:8b",
        messages=[
            {
                "role": "system",
                "content": "你是一个严谨、简洁的 AI 工程助手。",
            },
            {
                "role": "user",
                "content": "用三句话解释 RAG，并说明它和微调的区别。",
            },
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content
    reasoning = getattr(response.choices[0].message, "reasoning", None)

    mlflow.log_text(answer or "", "answer.txt")

    if reasoning:
        mlflow.log_text(reasoning, "reasoning.txt")

    print("Answer:")
    print(answer)

    if reasoning:
        print("\nReasoning:")
        print(reasoning)