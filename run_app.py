import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

uvicorn.run(
    "app:app",
    host="0.0.0.0",
    port=8000,
    reload=False
)