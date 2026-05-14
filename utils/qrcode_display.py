"""二维码生成 - 显示Gateway URL供用户扫码."""

import socket
import logging
import os

import qrcode

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """获取本机局域网IP地址."""
    # 先检查环境变量是否指定了IP
    env_ip = os.environ.get("GATEWAY_IP", "")
    if env_ip:
        return env_ip

    # 尝试获取局域网IP
    try:
        # macOS/Linux: 使用ifconfig或ip命令
        import subprocess
        result = subprocess.run(
            ["ifconfig"] if os.name != "nt" else ["ipconfig"],
            capture_output=True,
            text=True,
        )
        output = result.stdout

        # 查找en0或eth0的IP
        import re
        # 匹配 "inet xxx.xxx.xxx.xxx" 但排除 127.x.x.x
        matches = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", output)
        for ip in matches:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    # 默认返回localhost（用户需要手动设置GATEWAY_IP）
    return "127.0.0.1"


def list_available_ips() -> list[str]:
    """列出可用的IP地址."""
    ips = []
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
    except Exception:
        pass

    try:
        import subprocess
        import re
        result = subprocess.run(
            ["ifconfig"] if os.name != "nt" else ["ipconfig"],
            capture_output=True,
            text=True,
        )
        inet_ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
        for ip in inet_ips:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass

    return ips


def generate_qrcode(url: str) -> str:
    """生成二维码，返回ASCII字符串（用于终端显示）.

    Args:
        url: 要编码的URL

    Returns:
        ASCII二维码字符串
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # 生成ASCII二维码
    modules = qr.modules

    lines = []
    for row in modules:
        line = ""
        for cell in row:
            line += "██" if cell else "  "
        lines.append(line)

    return "\n".join(lines)


def print_gateway_qrcode(port: int = 8000, path: str = "/chat"):
    """打印Gateway二维码到终端.

    Args:
        port: Gateway端口
        path: 聊天页面路径
    """
    ip = get_local_ip()
    url = f"http://{ip}:{port}{path}"

    qr_ascii = generate_qrcode(url)

    print("\n" + "=" * 60)
    print("  AgentCraft Gateway 已启动")
    print("=" * 60)
    print(f"\n  扫描二维码打开聊天页面:\n")
    print(qr_ascii)
    print(f"\n  URL: {url}")
    print("\n" + "=" * 60 + "\n")

    logger.info(f"[Gateway] QR code URL: {url}")