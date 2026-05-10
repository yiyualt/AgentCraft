"""Interactive chat with local model via OpenAI-compatible API.

Usage:
    uv run python chat.py
    uv run python chat.py --model qwen3:8b --base-url http://127.0.0.1:8000/v1
    uv run python chat.py --session mychat
"""

import argparse
import sys
from openai import OpenAI

from sessions import SessionManager


def build_client(base_url: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key="ollama")


def _print_sessions(mgr: SessionManager) -> None:
    sessions = mgr.list_sessions()
    if not sessions:
        print("(no sessions)")
        return
    for s in sessions:
        marker = " [active]" if s.status == "active" else ""
        print(f"  {s.id}  {s.name}{marker}  ({s.message_count} msgs, {s.model})")


def repl(
    client: OpenAI,
    model: str,
    system_prompt: str | None,
    temperature: float = 0.3,
    session_name: str | None = None,
):
    mgr = SessionManager()
    session_id: str | None = None
    messages: list[dict] = []

    if session_name:
        # Find existing session by name
        existing = [s for s in mgr.list_sessions() if s.name == session_name]
        if existing:
            session = existing[0]
            session_id = session.id
            messages = mgr.get_messages_openai(session_id)
            print(f"Loaded session: {session_name} ({session.message_count} msgs)")
        else:
            session = mgr.create_session(name=session_name, model=model, system_prompt=system_prompt)
            session_id = session.id
            print(f"Created session: {session_name}")

    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    print(f"Model: {model}")
    print("Commands: /exit, /quit, /clear, /help, /sessions, /new <name>\n")

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        text = user_input.strip()
        if not text:
            continue

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd in ("/exit", "/quit"):
                break
            elif cmd == "/clear":
                messages = [m for m in messages if m["role"] == "system"]
                if session_id:
                    mgr.clear_messages(session_id)
                print("(history cleared)")
                continue
            elif cmd == "/help":
                print("Commands:")
                print("  /exit, /quit   退出")
                print("  /clear         清除对话历史")
                print("  /sessions      列出所有会话")
                print("  /new <name>    创建新会话")
                print("  /help          显示帮助")
                continue
            elif cmd == "/sessions":
                _print_sessions(mgr)
                continue
            elif cmd == "/new":
                name = parts[1] if len(parts) > 1 else "Untitled"
                session = mgr.create_session(name=name, model=model, system_prompt=system_prompt)
                session_id = session.id
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                print(f"Switched to new session: {name}")
                continue
            else:
                print(f"Unknown command: {cmd}")
                continue

        messages.append({"role": "user", "content": text})

        # Save user message locally
        if session_id:
            mgr.add_message(session_id=session_id, role="user", content=text)

        try:
            extra_headers = {}
            if session_id:
                extra_headers["X-Session-Id"] = session_id

            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=temperature,
                stream=False,
                extra_headers=extra_headers,
            )
            reply = response.choices[0].message.content or ""
            print(reply)
            messages.append({"role": "assistant", "content": reply})

            if session_id:
                mgr.add_message(session_id=session_id, role="assistant", content=reply)
        except Exception as e:
            print(f"[Error] {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Interactive chat with local model")
    parser.add_argument("--model", default="qwen3:8b", help="Model name (default: qwen3:8b)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--temperature", type=float, default=0.3, help="Sampling temperature (default: 0.3)")
    parser.add_argument("--system", help="Optional system prompt")
    parser.add_argument("--session", help="Session name (auto-create if not exists)")
    args = parser.parse_args()

    client = build_client(args.base_url)
    repl(client, args.model, args.system, args.temperature, args.session)


if __name__ == "__main__":
    main()
