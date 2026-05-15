"""Web tools: WebFetch, WebSearch."""

from __future__ import annotations

import re

import httpx

from tools import tool


@tool(
    name="WebFetch",
    description="Fetch and read the content of a URL. "
                "Use this to access web pages, APIs, or documentation. "
                "Returns the page content converted to markdown.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (including https://)",
            },
        },
        "required": ["url"],
    },
)
def web_fetch(url: str) -> str:
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        content = response.text
        # Simple HTML-to-text extraction for common cases
        if "<html" in content[:500].lower():
            # Remove scripts and styles
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            # Remove tags
            content = re.sub(r'<[^>]+>', ' ', content)
            # Collapse whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"

        return content[:10000]
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code}] {e.response.text[:500]}"
    except Exception as e:
        return f"[Error fetching URL] {e}"


@tool(
    name="WebSearch",
    description="Search the internet for current information. Uses DuckDuckGo — no API key required.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for '{query}'"
        lines = []
        for r in results:
            title = r.get("title", "")
            href = r.get("href", "")
            body = r.get("body", "")
            lines.append(f"- {title}\n  {href}\n  {body}")
        return "\n\n".join(lines)[:5000]
    except Exception as e:
        return f"[WebSearch error] {e}"


__all__ = ["web_fetch", "web_search"]