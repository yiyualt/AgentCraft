"""企业微信消息发送测试.

使用方法:
1. 在企业微信管理后台查看你的用户账号（通常是姓名拼音，如 "ZhangSan"）
2. 运行: python test_wecom.py <用户账号> <消息内容>

示例:
    python test_wecom.py ZhangSan "你好，这是测试消息"
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from channels.wecom import WeComChannel
from sessions.manager import SessionManager


async def test_send_message(user_id: str, message: str):
    """测试发送消息给企业微信用户."""
    session_manager = SessionManager()
    channel = WeComChannel(session_manager)

    # 启动channel（初始化WeChatClient）
    await channel.start()

    # 发送消息
    print(f"发送消息给 {user_id}: {message}")
    await channel.send_message(user_id, message)

    # 关闭channel
    await channel.stop()
    print("消息发送完成")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python test_wecom.py <用户账号> <消息内容>")
        print("示例: python test_wecom.py ZhangSan '测试消息'")
        sys.exit(1)

    user_id = sys.argv[1]
    message = sys.argv[2]

    asyncio.run(test_send_message(user_id, message))