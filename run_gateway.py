import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app import app
from utils.qrcode_display import print_gateway_qrcode

# 启动前显示二维码
print_gateway_qrcode(port=8000, path="/chat")

# 启动服务器
uvicorn.run(app, host="0.0.0.0", port=8000)
