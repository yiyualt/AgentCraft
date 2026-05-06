"""Interactive chat with local model via OpenAI-compatible API.

Usage:
    uv run python chat.py
    uv run python chat.py --model qwen3:8b --base-url http://127.0.0.1:8000/v1
"""

import argparse
import sys
from openai import OpenAI


def build_client(base_url: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key="ollama")


def repl(client: OpenAI, model: str, system_prompt: str | None, temperature: float = 0.3):
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    print(f"Model: {model}")
    print("Type /exit or /quit to quit, /clear to clear history, /help for commands.\n")

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
            cmd = text.lower()
            if cmd in ("/exit", "/quit"):
                break
            elif cmd == "/clear":
                messages.clear()
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                print("(history cleared)")
                continue
            elif cmd == "/help":
                print("Commands:")
                print("  /exit, /quit  退出")
                print("  /clear        清除对话历史")
                print("  /help         显示帮助")
                continue
            else:
                print(f"Unknown command: {cmd}")
                continue

        messages.append({"role": "user", "content": text})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=temperature,
                stream=False,
            )
            reply = response.choices[0].message.content or ""
            print(reply)
            messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"[Error] {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Interactive chat with local model")
    parser.add_argument("--model", default="qwen3:8b", help="Model name (default: qwen3:8b)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--temperature", type=float, default=0.3, help="Sampling temperature (default: 0.3)")
    parser.add_argument("--system", help="Optional system prompt")
    args = parser.parse_args()

    client = build_client(args.base_url)
    repl(client, args.model, args.system, args.temperature)


if __name__ == "__main__":
    main()
