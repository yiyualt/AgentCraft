"""Token counting tool."""

from __future__ import annotations

from tools import tool


@tool(
    name="CountTokens",
    description="Count the number of tokens in a text string using tiktoken (cl100k_base encoding).",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to count tokens for",
            },
        },
        "required": ["text"],
    },
)
def count_tokens(text: str) -> str:
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        token_count = len(encoding.encode(text))
        char_count = len(text)
        return f"文本: '{text[:50]}...' (共 {char_count} 字符)\nToken 数: {token_count}"
    except Exception as e:
        return f"[Error counting tokens] {e}"


__all__ = ["count_tokens"]