import os
import subprocess
import socket
import time
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ===== Configuration =====
MLFLOW_PORT = 5050
REDIS_PORT = 6379
APP_PORT = 8000
WORKERS = int(os.getenv("APP_WORKERS", "8"))


def is_port_open(port: int) -> bool:
    """Check if a port is already in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result == 0


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Wait for port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            return True
        time.sleep(0.5)
    return False


def start_mlflow():
    """Start MLflow server if not running."""
    if is_port_open(MLFLOW_PORT):
        print(f"[MLflow] Already running on port {MLFLOW_PORT}")
        return

    print(f"[MLflow] Starting on port {MLFLOW_PORT}...")
    subprocess.Popen(
        [
            "mlflow",
            "server",
            "--host",
            "127.0.0.1",
            "--port",
            str(MLFLOW_PORT),
            "--backend-store-uri",
            "sqlite:///mlflow.db",
            "--default-artifact-root",
            "./mlartifacts",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if wait_for_port(MLFLOW_PORT, timeout=15.0):
        print(f"[MLflow] Started successfully")
    else:
        print(f"[MLflow] Warning: startup timeout, continuing anyway...")


def start_redis():
    """Start Redis server if not running."""
    if is_port_open(REDIS_PORT):
        print(f"[Redis] Already running on port {REDIS_PORT}")
        return

    print(f"[Redis] Starting on port {REDIS_PORT}...")
    subprocess.Popen(
        ["redis-server", "--daemonize", "yes"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if wait_for_port(REDIS_PORT, timeout=5.0):
        print(f"[Redis] Started successfully")
    else:
        print(f"[Redis] Warning: startup timeout, continuing anyway...")


def main():
    print("=" * 50)
    print("AgentCraft Gateway Startup")
    print("=" * 50)

    # Start dependencies
    start_mlflow()
    start_redis()

    print(f"\n[App] Starting with {WORKERS} workers on port {APP_PORT}...")
    print("=" * 50)

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=APP_PORT,
        workers=WORKERS,
    )


if __name__ == "__main__":
    main()