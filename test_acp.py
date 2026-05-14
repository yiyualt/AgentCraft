"""ACP测试 - 验证AgentControlPlane功能."""

import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import httpx

from tools import UnifiedToolRegistry, get_default_registry
from tools.builtin import *  # 注册内置tools
from sessions import SessionManager, ForkManager
from acp import AgentControlPlane, AcpConfig, AcpEvent, AcpEventType


async def test_acp():
    """测试ACP基本功能."""
    print("=" * 60)
    print("ACP Control Plane 测试")
    print("=" * 60)

    # 初始化组件
    client = OpenAI(
        base_url="https://api.deepseek.com",
        api_key=os.getenv("LLM_API_KEY"),
        http_client=httpx.Client(trust_env=False, timeout=300),
    )

    session_manager = SessionManager()
    registry = UnifiedToolRegistry(get_default_registry())
    fork_manager = ForkManager(session_manager=session_manager, token_calculator=None)

    # 创建ACP
    config = AcpConfig(
        max_children=5,
        default_timeout=120,
        recursion_protection=True,
    )

    acp = AgentControlPlane(
        llm_client=client,
        registry=registry,
        session_manager=session_manager,
        fork_manager=fork_manager,
        config=config,
        model="deepseek-chat",
    )

    print(f"\nACP配置:")
    print(f"  max_children: {config.max_children}")
    print(f"  timeout: {config.default_timeout}s")
    print(f"  recursion_protection: {config.recursion_protection}")

    # 测试1: 派发单个子Agent
    print("\n" + "-" * 60)
    print("测试1: 派发单个子Agent")
    print("-" * 60)

    handle = acp.spawn_child(
        task="列出当前目录下的Python文件",
        agent_type="explore",
    )

    print(f"子Agent已派发: {handle.child_id}")
    print(f"状态: {handle.state.value}")

    # 监听事件流
    event_count = 0
    async for event in acp.parent_stream():
        event_count += 1
        print(f"  [{event.event_type.value}] {event.child_id}: {str(event.data)[:50]}...")

        if event.event_type == AcpEventType.COMPLETED:
            print(f"\n结果: {event.data.get('result', '')[:100]}...")
            break

        # 限制事件数量防止无限循环
        if event_count > 50:
            print("事件过多，停止监听")
            break

    # 测试2: 查看状态
    print("\n" + "-" * 60)
    print("测试2: ACP状态")
    print("-" * 60)

    status = acp.get_status()
    print(f"总派发数: {status['total_spawned']}")
    print(f"活跃数: {status['active']}")
    print(f"完成数: {status['completed']}")
    print(f"失败数: {status['failed']}")

    # 测试3: 并行派发多个子Agent
    print("\n" + "-" * 60)
    print("测试3: 并行派发多个子Agent")
    print("-" * 60)

    tasks = [
        ("查看README.md内容", "explore"),
        ("检查gateway.py有多少行", "explore"),
        ("列出tools目录的文件", "explore"),
    ]

    handles = []
    for task, agent_type in tasks:
        handle = acp.spawn_child(task=task, agent_type=agent_type)
        handles.append(handle)
        print(f"派发: {handle.child_id} - {task}")

    # 等待所有完成
    print("\n等待所有子Agent完成...")
    results = await acp.wait_all(timeout=120)

    print("\n结果汇总:")
    for child_id, result in results.items():
        print(f"  {child_id}: {result[:80]}...")

    # 最终状态
    print("\n" + "-" * 60)
    print("最终状态")
    print("-" * 60)
    status = acp.get_status()
    print(f"完成: {status['completed']}/{status['total_spawned']}")


if __name__ == "__main__":
    asyncio.run(test_acp())