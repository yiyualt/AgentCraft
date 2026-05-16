"""Stream Handler - bridges LLMQueue with ProviderRegistry.

Converts Provider async stream to SSE format for gateway responses.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class StreamHandler:
    """Handles streaming LLM responses with provider integration.

    Responsibilities:
    - Call ProviderRegistry.stream_iterator()
    - Accumulate tool_calls from stream chunks
    - Generate SSE events in gateway format
    """

    def __init__(self, provider_registry: Any):
        self._registry = provider_registry

    def handle_streaming_request(
        self,
        request: Any,  # QueuedRequest
    ) -> AsyncIterator[str]:
        """Handle streaming request using ProviderRegistry.

        Yields SSE events. Accumulates result in request._stream_result.
        """
        return self._stream_generator(request)

    async def _stream_generator(self, request: Any) -> AsyncIterator[str]:
        """Async generator for SSE stream."""
        messages = request.messages
        model = request.model
        kwargs = request.kwargs
        request_id = request.request_id

        # Yield start event
        yield f"event: stream_request_start\ndata: {{\"model\": \"{model}\", \"request_id\": \"{request_id}\"}}\n\n"

        # Accumulators
        full_content = ""
        tool_calls_list: list[dict] = []
        finish_reason = None

        try:
            # Get stream iterator from registry
            stream = self._registry.stream_iterator(messages, model, stream=True, **kwargs)

            # Iterate over stream chunks
            for chunk in stream:
                choices = chunk.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})

                # Stream content
                if delta.get("content"):
                    text = delta["content"]
                    full_content += text
                    # Escape for JSON
                    escaped = text.replace('"', '\\"').replace('\n', '\\n').replace('\r', '')
                    yield f"data: {{\"text\": \"{escaped}\"}}\n\n"

                # Accumulate tool calls
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        while idx >= len(tool_calls_list):
                            tool_calls_list.append({
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                        if tc.get("id"):
                            tool_calls_list[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_list[idx]["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_calls_list[idx]["function"]["arguments"] += fn["arguments"]

                        # Yield tool_start event
                        if fn.get("name"):
                            yield f"event: tool_start\ndata: {{\"id\": \"{tc.get('id')}\", \"name\": \"{fn['name']}\"}}\n\n"

                # Finish reason
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

            # Stream complete
            yield f"data: {{\"finish_reason\": \"{finish_reason or 'stop'}\"}}\n\n"

            # Store result for tool handling
            request._stream_result = {
                "content": full_content,
                "tool_calls": tool_calls_list,
                "finish_reason": finish_reason,
            }

            logger.info(
                f"[StreamHandler] Request {request_id} completed: "
                f"content_len={len(full_content)}, tools={len(tool_calls_list)}"
            )

        except Exception as e:
            logger.error(f"[StreamHandler] Stream error for {request_id}: {e}")
            request._stream_error = str(e)
            yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"


__all__ = ["StreamHandler"]