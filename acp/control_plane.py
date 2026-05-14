"""ACP Control Plane - Agent控制平面核心.

管理子Agent的创建、执行、监控和结果聚合。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, AsyncIterator

from openai import OpenAI

from tools import UnifiedToolRegistry
from tools.agent_executor import AGENT_TYPES
from sessions import SessionManager, ForkManager, ForkContext, TokenCalculator
from acp.types import (
    AcpConfig,
    AcpSessionState,
    AcpEvent,
    AcpEventType,
    ChildAgentHandle,
)

logger = logging.getLogger(__name__)


class AgentControlPlane:
    """Agent控制平面 - 管理子Agent的派发和聚合.

    核心功能:
    - spawn_child(): 创建并派发子Agent执行任务
    - parent_stream(): 聚合所有子Agent的实时输出
    - send_to_child(): 向特定子Agent发送消息
    - broadcast(): 向所有子Agent广播消息
    - wait_all(): 等待所有子Agent完成并收集结果

    约束:
    - 子Agent数量限制（默认max 10）
    - 超时控制（默认180s）
    - 递归保护（子Agent不能再spawn）
    - 上下文继承限制（默认32000 tokens）
    """

    def __init__(
        self,
        llm_client: OpenAI,
        registry: UnifiedToolRegistry,
        session_manager: SessionManager,
        fork_manager: ForkManager | None = None,
        config: AcpConfig | None = None,
        model: str = "deepseek-chat",
    ):
        self._client = llm_client
        self._registry = registry
        self._session_manager = session_manager
        self._fork_manager = fork_manager
        self._config = config or AcpConfig()
        self._model = model
        self._token_calculator = TokenCalculator()

        # 子Agent管理
        self._children: OrderedDict[str, ChildAgentHandle] = OrderedDict()
        self._event_queue: asyncio.Queue[AcpEvent] = asyncio.Queue()
        self._tasks: dict[str, asyncio.Task] = {}

        logger.info(f"[ACP] ControlPlane initialized: max_children={self._config.max_children}")

    def spawn_child(
        self,
        task: str,
        agent_type: str = "general-purpose",
        context: str | None = None,
        timeout: int | None = None,
        parent_messages: list[dict] | None = None,
    ) -> ChildAgentHandle:
        """派发一个子Agent执行任务.

        Args:
            task: 子Agent要执行的任务
            agent_type: Agent类型（explore, general-purpose, plan）
            context: 附加上下文信息
            timeout: 超时时间（秒），默认使用config.default_timeout
            parent_messages: 父对话上下文（用于继承）

        Returns:
            ChildAgentHandle: 子Agent句柄，用于跟踪和通信

        Raises:
            ValueError: 超过子Agent数量限制
        """
        # 检查数量限制
        active_count = sum(
            1 for h in self._children.values()
            if not h.is_terminal()
        )
        if active_count >= self._config.max_children:
            raise ValueError(
                f"Maximum child agents limit reached ({self._config.max_children}). "
                f"Active: {active_count}"
            )

        # 生成子Agent ID
        child_id = f"child-{uuid.uuid4().hex[:8]}"
        timeout_seconds = timeout or self._config.default_timeout

        # 创建句柄
        handle = ChildAgentHandle(
            child_id=child_id,
            task=task,
            agent_type=agent_type,
            state=AcpSessionState.IDLE,
            started_at=time.time(),
        )

        self._children[child_id] = handle

        # 创建ForkContext（继承父对话）
        fork_context = None
        if parent_messages and self._fork_manager:
            # 检查上下文大小限制
            tokens = self._token_calculator.count_messages(parent_messages)
            if tokens > self._config.context_inheritance_limit:
                # 需要压缩或裁剪
                parent_messages = self._trim_messages(
                    parent_messages,
                    self._config.context_inheritance_limit,
                )
                logger.info(f"[ACP] Trimmed parent context to {self._config.context_inheritance_limit} tokens")

            fork_context = ForkContext(
                parent_session_id="parent",  # 虚拟parent ID
                inherited_messages=parent_messages,
            )

        # 启动子Agent任务
        task_coro = self._run_child_agent(
            child_id=child_id,
            task=task,
            agent_type=agent_type,
            context=context,
            timeout=timeout_seconds,
            fork_context=fork_context,
        )
        self._tasks[child_id] = asyncio.create_task(task_coro)

        # 发送启动事件
        self._emit_event(AcpEvent(
            child_id=child_id,
            event_type=AcpEventType.STARTED,
            data={"task": task, "agent_type": agent_type},
        ))

        logger.info(f"[ACP] Spawned child {child_id}: task='{task[:50]}...', type={agent_type}")
        return handle

    async def _run_child_agent(
        self,
        child_id: str,
        task: str,
        agent_type: str,
        context: str | None,
        timeout: int,
        fork_context: ForkContext | None,
    ) -> str:
        """执行子Agent任务."""
        handle = self._children[child_id]
        handle.state = AcpSessionState.RUNNING

        try:
            # 构建子Agent消息
            messages = self._build_child_messages(
                task=task,
                agent_type=agent_type,
                context=context,
                fork_context=fork_context,
            )

            # 获取Agent类型配置
            agent_config = self._get_agent_config(agent_type)

            # 获取可用Tools（递归保护：移除Agent tool）
            tools = self._get_child_tools(agent_config)

            # 执行循环（带超时）
            result = await asyncio.wait_for(
                self._execute_child_loop(child_id, messages, tools, agent_config),
                timeout=timeout,
            )

            # 完成
            handle.state = AcpSessionState.COMPLETED
            handle.result = result

            self._emit_event(AcpEvent(
                child_id=child_id,
                event_type=AcpEventType.COMPLETED,
                data={"result": result},
            ))

            logger.info(f"[ACP] Child {child_id} completed")
            return result

        except asyncio.TimeoutError:
            handle.state = AcpSessionState.TIMEOUT
            handle.error = f"Timeout after {timeout}s"

            self._emit_event(AcpEvent(
                child_id=child_id,
                event_type=AcpEventType.TIMEOUT,
                data={"timeout": timeout},
            ))

            logger.warning(f"[ACP] Child {child_id} timed out after {timeout}s")
            return f"[TIMEOUT] Task exceeded {timeout}s limit"

        except Exception as e:
            handle.state = AcpSessionState.FAILED
            handle.error = str(e)

            self._emit_event(AcpEvent(
                child_id=child_id,
                event_type=AcpEventType.FAILED,
                data={"error": str(e)},
            ))

            logger.error(f"[ACP] Child {child_id} failed: {e}")
            return f"[ERROR] {str(e)}"

    async def _execute_child_loop(
        self,
        child_id: str,
        messages: list[dict],
        tools: list[dict],
        agent_config: dict,
    ) -> str:
        """执行子Agent的Tool循环."""
        max_turns = agent_config.get("max_turns", 10)
        final_content = ""

        for turn in range(max_turns):
            # 调用LLM
            try:
                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=self._model,
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                logger.error(f"[ACP] Child {child_id} LLM error: {e}")
                raise

            choice = response.choices[0]
            message = choice.message
            messages.append(message.model_dump())

            # 发送内容事件
            if message.content:
                self._emit_event(AcpEvent(
                    child_id=child_id,
                    event_type=AcpEventType.CONTENT,
                    data={"content": message.content},
                ))
                final_content = message.content

            # 检查Tool Call
            tool_calls = message.tool_calls
            if not tool_calls:
                break

            # 执行Tools
            for tc in tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                # 发送Tool调用事件
                self._emit_event(AcpEvent(
                    child_id=child_id,
                    event_type=AcpEventType.TOOL_CALL,
                    data={"name": fn_name, "args": fn_args},
                ))

                # 执行Tool
                tool_result = await self._execute_tool(fn_name, fn_args)

                # 发送Tool结果事件
                self._emit_event(AcpEvent(
                    child_id=child_id,
                    event_type=AcpEventType.TOOL_RESULT,
                    data={"name": fn_name, "result": tool_result[:200]},
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        return final_content

    async def _execute_tool(self, name: str, args: dict) -> str:
        """执行Tool."""
        # dispatch是async方法，需要await
        result = await self._registry.dispatch(name, args)
        return str(result)

    def _build_child_messages(
        self,
        task: str,
        agent_type: str,
        context: str | None,
        fork_context: ForkContext | None,
    ) -> list[dict]:
        """构建子Agent的消息列表."""
        messages = []

        # System Prompt
        agent_config = self._get_agent_config(agent_type)
        system_prompt = self._build_child_system_prompt(agent_config, context, fork_context)
        messages.append({"role": "system", "content": system_prompt})

        # 继承父对话（如果有）
        if fork_context:
            for msg in fork_context.inherited_messages:
                messages.append(msg)

        # 用户任务
        messages.append({"role": "user", "content": task})

        return messages

    def _build_child_system_prompt(
        self,
        agent_config: dict,
        context: str | None,
        fork_context: ForkContext | None,
    ) -> str:
        """构建子Agent的System Prompt."""
        lines = []

        # 递归保护提示
        if self._config.recursion_protection:
            lines.append(
                "STOP. READ THIS FIRST.\n"
                "You are a child worker. You are NOT the main agent.\n\n"
                "RULES:\n"
                "1. Do NOT spawn sub-agents (Agent tool disabled)\n"
                "2. Do NOT ask questions - execute directly\n"
                "3. Report findings once at the end, be concise\n"
                "4. Stay within your assigned scope\n"
            )

        # Agent描述
        lines.append(f"\nTask Scope: {agent_config.get('description', 'General execution')}")

        # 附加上下文
        if context:
            lines.append(f"\nAdditional Context:\n{context}")

        return "\n".join(lines)

    def _get_agent_config(self, agent_type: str) -> dict:
        """获取Agent类型配置."""
        return AGENT_TYPES.get(agent_type, AGENT_TYPES["general-purpose"])

    def _get_child_tools(self, agent_config: dict) -> list[dict]:
        """获取子Agent可用的Tools（移除Agent tool防止递归）."""
        all_tools = self._registry.list_tools()

        if self._config.recursion_protection:
            # 移除Agent tool
            filtered = [t for t in all_tools if t.get("function", {}).get("name") != "Agent"]
            return filtered

        # 如果配置允许特定Tools
        allowed = agent_config.get("tools")
        if allowed:
            return [t for t in all_tools if t.get("function", {}).get("name") in allowed]

        return all_tools

    def _trim_messages(self, messages: list[dict], max_tokens: int) -> list[dict]:
        """裁剪消息以符合token限制."""
        # 保留system + 最近消息
        trimmed = []

        # 保留system消息
        for msg in messages:
            if msg.get("role") == "system":
                trimmed.append(msg)

        # 从末尾添加消息直到达到限制
        calculator = TokenCalculator()
        current_tokens = calculator.count_messages(trimmed)

        for msg in reversed([m for m in messages if m.get("role") != "system"]):
            msg_tokens = calculator.count_messages([msg])
            if current_tokens + msg_tokens <= max_tokens:
                trimmed.append(msg)
                current_tokens += msg_tokens
            else:
                break

        # 恢复顺序
        system_msgs = [m for m in trimmed if m.get("role") == "system"]
        other_msgs = [m for m in trimmed if m.get("role") != "system"]
        other_msgs.reverse()

        return system_msgs + other_msgs

    def _emit_event(self, event: AcpEvent) -> None:
        """发送事件到队列."""
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"[ACP] Event queue full, dropping event: {event.event_type}")

    # ===== 公共API: 父子通信 =====

    async def parent_stream(self) -> AsyncIterator[AcpEvent]:
        """聚合所有子Agent的事件流.

        实时接收所有子Agent的进度、Tool调用、内容输出等事件。
        """
        while True:
            # 检查是否所有子Agent都已结束
            all_terminal = all(h.is_terminal() for h in self._children.values())

            if all_terminal and self._event_queue.empty():
                break

            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue

    def send_to_child(self, child_id: str, message: str) -> bool:
        """向特定子Agent发送消息.

        注意: 只能在子Agent运行期间发送，用于动态指导。
        如果子Agent已结束，返回False。
        """
        handle = self._children.get(child_id)
        if not handle or handle.is_terminal():
            return False

        # 发送事件（子Agent需要监听）
        self._emit_event(AcpEvent(
            child_id=child_id,
            event_type=AcpEventType.CONTENT,
            data={"parent_message": message},
        ))

        return True

    def broadcast(self, message: str) -> int:
        """向所有活跃子Agent广播消息.

        Returns:
            成功发送的子Agent数量
        """
        count = 0
        for child_id, handle in self._children.items():
            if not handle.is_terminal():
                if self.send_to_child(child_id, message):
                    count += 1

        return count

    async def wait_all(self, timeout: float | None = None) -> dict[str, str]:
        """等待所有子Agent完成并收集结果.

        Args:
            timeout: 总超时时间（None表示等待所有完成）

        Returns:
            {child_id: result} 结果字典
        """
        results = {}

        # 等待所有任务完成
        tasks = list(self._tasks.values())

        if timeout:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        else:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果
        for child_id, handle in self._children.items():
            if handle.state == AcpSessionState.COMPLETED:
                results[child_id] = handle.result or ""
            else:
                results[child_id] = f"[{handle.state.value}] {handle.error or ''}"

        return results

    def get_status(self) -> dict[str, Any]:
        """获取ACP状态快照."""
        active = sum(1 for h in self._children.values() if not h.is_terminal())
        completed = sum(1 for h in self._children.values() if h.state == AcpSessionState.COMPLETED)
        failed = sum(1 for h in self._children.values() if h.state in (AcpSessionState.FAILED, AcpSessionState.TIMEOUT))

        return {
            "total_spawned": len(self._children),
            "active": active,
            "completed": completed,
            "failed": failed,
            "max_children": self._config.max_children,
            "children": {
                child_id: {
                    "task": handle.task[:50],
                    "state": handle.state.value,
                    "elapsed": handle.elapsed_seconds(),
                }
                for child_id, handle in self._children.items()
            },
        }