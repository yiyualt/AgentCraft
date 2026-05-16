import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app import app

# 启动服务器
uvicorn.run(app, host="0.0.0.0", port=8000)