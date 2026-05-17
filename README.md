# AgentCraft Gateway

AI Agent with LLM and tools.

## 快速启动

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -e .

# 3. 配置环境变量
cp ".env copy" .env
# 编辑 .env 填入你的 API Key

# 4. 启动服务
python run_app.py
```

服务将在 http://127.0.0.1:8000 启动。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | LLM API 密钥 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `MLFLOW_TRACKING_URI` | MLflow 追踪地址 (默认 http://127.0.0.1:5050) |