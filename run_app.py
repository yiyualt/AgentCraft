import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app import app

# 启动服务器（多worker模式避免阻塞）
# workers=4: 允许4个并发请求同时处理
# 当一个worker处理streaming对话时，其他worker可以处理canvas访问等请求
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=32,  # 多worker模式，避免单worker阻塞
)