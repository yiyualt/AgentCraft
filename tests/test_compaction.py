#!/usr/bin/env python3
"""Test auto-compaction trigger by creating a long conversation."""

import httpx
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def create_session(name: str) -> str:
    """Create a new session."""
    response = httpx.post(
        f"{BASE_URL}/v1/sessions",
        json={"name": name},
    )
    data = response.json()
    return data["id"]

def send_message(session_id: str, content: str) -> str:
    """Send a message and get response."""
    response = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"X-Session-Id": session_id},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": content}],
        },
        timeout=120,
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]

def add_message_directly(session_id: str, role: str, content: str):
    """Add a message directly to session (for testing large history)."""
    # Use the gateway's internal message addition
    # We'll send a request that adds the message without triggering LLM
    response = httpx.post(
        f"{BASE_URL}/v1/sessions/{session_id}/messages",
        json={"role": role, "content": content},
    )
    return response.json()

def get_session_info(session_id: str) -> dict:
    """Get session info including token count."""
    response = httpx.get(f"{BASE_URL}/v1/sessions/{session_id}")
    return response.json()

def main():
    print("=== Auto-Compaction Test ===")

    # Create session
    session_id = create_session("compaction-test")
    print(f"Session created: {session_id}")

    # Get initial session info
    session_info = get_session_info(session_id)
    print(f"Initial context_window: {session_info.get('context_window', 64000)}")

    # Add many messages to increase token count
    # We need ~38000+ tokens to trigger 60% threshold
    # Each message with ~1000 chars ≈ 250-300 tokens

    print("\nAdding messages to increase token count...")
    large_content = """
This is a test message for auto-compaction. We need to create enough content
to exceed the 60% threshold of the context window (64000 tokens).

The content includes:
- Technical details about the system
- Code snippets and examples
- Detailed explanations of various components
- Historical context about the project

We're testing the CompactionManager which has three levels:
1. Microcompact (60% threshold) - simple truncation
2. Autocompact (80% threshold) - LLM summarization
3. Reactive (90% threshold) - aggressive compression

The circuit breaker stops after 3 consecutive failures.
The cooldown period is 60 seconds before retry.

Key files modified:
- sessions/compaction.py - CompactionManager implementation
- sessions/fork.py - ForkManager implementation
- gateway.py - Integration with conversation loop
- tools/agent_executor.py - Fork support
- tools/builtin.py - Agent tool fork_from_current parameter

This message is approximately 500 tokens. We need many such messages.
""" * 2  # ~1000 tokens per message

    # Add 80 messages (~80000 tokens total, exceeding 64K context window)
    for i in range(80):
        # Alternate between user and assistant
        role = "user" if i % 2 == 0 else "assistant"
        content = f"[Message {i+1}] {large_content}"

        # Use direct message addition (faster than LLM calls)
        try:
            result = add_message_directly(session_id, role, content)
            print(f"Added message {i+1}, token_count: {result.get('token_count', 'N/A')}")
        except Exception as e:
            print(f"Error adding message {i+1}: {e}")
            break

    # Check session token count
    session_info = get_session_info(session_id)
    print(f"\nSession token_count: {session_info.get('token_count', 'N/A')}")
    print(f"Session message_count: {session_info.get('message_count', 'N/A')}")

    # Now send a real message to trigger LLM call (and compaction check)
    print("\nSending trigger message...")
    response = send_message(session_id, "Please summarize what we discussed.")
    print(f"Response: {response[:200]}...")

    # Check logs for compaction
    print("\n=== Check gateway.log for COMPACTION logs ===")
    print("Expected: [COMPACTION] Level X triggered for session...")
    print("Expected: [COMPACTION] Level X complete, tokens_saved=...")

    print(f"\nSession ID for log search: {session_id}")

if __name__ == "__main__":
    main()