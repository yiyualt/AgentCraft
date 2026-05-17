"""MemoryExtractor - Auto extract valuable information from conversations.

Triggered every 5 user messages, analyzes recent 20 messages and saves
worth-remembering content to memory.db.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from tools.builtin.memory_tools import remember, _infer_memory_type

logger = logging.getLogger("gateway")


class MemoryExtractor:
    """Auto extracts memories from conversation messages."""

    def __init__(self, llm_client: Any, model: str = "deepseek-chat"):
        self._llm_client = llm_client
        self._model = model

    async def analyze_and_save(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Analyze messages and save worth-remembering content.

        Args:
            session_id: Session ID (for logging)
            messages: Recent messages to analyze (up to 20)
        """
        # Step 1: LLM analysis (direct, no keyword filter)
        memory_content = await self._llm_analyze(messages)
        if not memory_content:
            logger.debug(f"[MemoryExtractor] LLM found no worth-remembering content")
            return

        # Step 2: Infer type
        memory_type = self._infer_type(memory_content)

        # Step 3: Save
        await self._save_memory(memory_content, memory_type)
        logger.info(f"[MemoryExtractor] Saved memory: {memory_content[:50]}...")

    async def _llm_analyze(self, messages: list[dict[str, Any]]) -> str | None:
        """Call LLM to judge if content is worth remembering.

        Returns:
            Memory content if worth saving, None otherwise
        """
        # Build prompt
        content_lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content:
                content_lines.append(f"[{role}]: {content}")

        conversation = "\n".join(content_lines[:20])  # Limit to 20 messages

        prompt = f"""分析以下对话，判断是否有值得长期记忆的内容。

对话内容：
{conversation}

判断标准：
1. 用户明确表达了偏好或习惯（如"我喜欢简洁的回答"、"不要用emoji"）
2. 用户提到了项目约束或工作习惯（如"我们团队的代码风格是..."）
3. 用户给出了反馈或纠正（如"不要这样，要那样"）

如果有值得记忆的内容，请提取并简要总结（一句话）。
如果没有，请回复 "无"。

只回复记忆内容或"无"，不要解释。"""

        try:
            response = await asyncio.to_thread(
                self._llm_client.chat.completions.create,
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )

            result = response.choices[0].message.content.strip()
            if result == "无" or not result:
                return None
            return result

        except Exception as e:
            logger.error(f"[MemoryExtractor] LLM analysis failed: {e}")
            return None

    def _infer_type(self, content: str) -> str:
        """Infer memory type from content.

        Args:
            content: Memory content

        Returns:
            Memory type (user/feedback/project/reference)
        """
        return _infer_memory_type(content)

    async def _save_memory(self, content: str, memory_type: str) -> None:
        """Save memory using memory_tools.remember().

        Args:
            content: Memory content
            memory_type: Memory type
        """
        try:
            # Generate unique name from content (first 20 chars, sanitized)
            import time
            import re
            # Extract meaningful words (Chinese or English)
            words = re.findall(r'[一-龥]+|[a-zA-Z]+', content[:50])
            if words:
                name_base = '-'.join(words[:3]).lower()
            else:
                name_base = "auto"
            # Add timestamp suffix to ensure uniqueness
            unique_name = f"{name_base}-{int(time.time())}"

            # Call remember tool (async)
            await remember(content=content, name=unique_name, memory_type=memory_type)
        except Exception as e:
            logger.error(f"[MemoryExtractor] Failed to save memory: {e}")


__all__ = ["MemoryExtractor"]