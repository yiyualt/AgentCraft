#!/usr/bin/env python3
"""Test fork mode - Agent inherits parent conversation context."""

import httpx
import json

BASE_URL = "http://127.0.0.1:8000"

def create_session(name: str) -> str:
    """Create a new session."""
    response = httpx.post(
        f"{BASE_URL}/v1/sessions",
        json={"name": name},
    )
    data = response.json()
    return data["id"]

def send_message(session_id: str, content: str) -> dict:
    """Send a message and get full response (streaming)."""
    response = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"X-Session-Id": session_id},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": content}],
            "stream": True,
        },
        timeout=120,
    )
    # Parse streaming response
    full_content = ""
    for line in response.iter_lines():
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                if data.get("text"):
                    full_content += data["text"]
                if data.get("finish_reason") == "stop":
                    break
            except json.JSONDecodeError:
                continue
    # Return in same format for compatibility
    return {"choices": [{"message": {"content": full_content}}]}

def get_session_messages(session_id: str) -> list:
    """Get session messages."""
    response = httpx.get(f"{BASE_URL}/v1/sessions/{session_id}/messages")
    return response.json()

def main():
    print("=== Fork Mode Test ===")

    # Create a session with conversation history
    session_id = create_session("fork-test")
    print(f"Session created: {session_id}")

    # Add some conversation context
    print("\nAdding conversation context...")

    # First message - establish context about a project
    response1 = send_message(
        session_id,
        "I'm working on a Python project called AgentCraft. It's an agent framework with tools, sessions, and compaction features. We just implemented auto-compaction and fork mechanism."
    )
    print(f"Response 1: {response1['choices'][0]['message']['content'][:100]}...")

    # Second message - more context
    response2 = send_message(
        session_id,
        "The compaction system has three levels: Microcompact at 60%, Autocompact at 80%, and Reactive at 90%. The Fork mechanism allows sub-agents to inherit parent context."
    )
    print(f"Response 2: {response2['choices'][0]['message']['content'][:100]}...")

    # Check session has messages
    messages = get_session_messages(session_id)
    print(f"\nSession has {len(messages)} messages")

    # Now test fork mode - ask agent to do something with fork_from_current=true
    # The agent should inherit the conversation context
    print("\n=== Testing Fork Mode ===")

    # Clear logs
    import subprocess
    subprocess.run(["bash", "-c", "> logs/gateway.log"])

    # Request with fork_from_current
    fork_request = """
Use the Agent tool with fork_from_current=true to summarize what we discussed about AgentCraft.
The forked agent should inherit our conversation context and be able to reference the compaction levels we discussed.
"""

    response3 = send_message(session_id, fork_request)
    print(f"Response 3: {response3['choices'][0]['message']['content'][:200]}...")

    # Check logs for FORK
    print("\n=== Checking FORK logs ===")
    result = subprocess.run(
        ["grep", "FORK", "logs/gateway.log"],
        capture_output=True,
        text=True,
    )
    print(result.stdout[:500] if result.stdout else "No FORK logs found")

    # Check if Agent tool was called
    result = subprocess.run(
        ["grep", "-E", "Agent|fork_from_current", "logs/gateway.log"],
        capture_output=True,
        text=True,
    )
    print("\n=== Agent tool logs ===")
    print(result.stdout[:500] if result.stdout else "No Agent tool logs found")

    print(f"\nSession ID for log search: {session_id}")

if __name__ == "__main__":
    main()