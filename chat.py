"""Interactive chat with local model via OpenAI-compatible API.

Usage:
    uv run python chat.py
    uv run python chat.py --model qwen3:8b --base-url http://127.0.0.1:8000/v1
    uv run python chat.py --session mychat
"""

import argparse
import os
import sys
import logging
from openai import OpenAI

from sessions import SessionManager

# ===== Logging (写入文件) =====
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "chat.log")

logger = logging.getLogger("chat")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


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
        existing = [s for s in mgr.list_sessions() if s.name == session_name]
        if existing:
            session = existing[0]
            session_id = session.id
            messages = mgr.get_messages_openai(session_id)
            print(f"Loaded session: {session_name} ({session.message_count} msgs)")
            logger.info(f"Loaded session: {session_name} ({session.message_count} msgs), id={session_id}")
        else:
            session = mgr.create_session(name=session_name, model=model, system_prompt=system_prompt)
            session_id = session.id
            print(f"Created session: {session_name}")
            logger.info(f"Created session: {session_name}, id={session_id}, model={model}")

    active_sp = None
    if session_id:
        s = mgr.get_session(session_id)
        if s and s.system_prompt:
            active_sp = s.system_prompt
    elif system_prompt:
        active_sp = system_prompt

    if active_sp:
        print(f"System: {active_sp}")
        logger.info(f"Active system_prompt: {active_sp}")

    print(f"Model: {model}")
    print("Commands: /exit, /quit, /clear, /help, /sessions, /new <name>, /system, /skills\n")
    logger.info(f"REPL started, model={model}, session_id={session_id}")

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            logger.info("REPL exiting (EOF/Interrupt)")
            break

        text = user_input.strip()
        if not text:
            continue

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            logger.info(f"Command received: {cmd}, full_input='{text}'")

            if cmd in ("/exit", "/quit"):
                logger.info("REPL exiting (/exit or /quit)")
                break
            elif cmd == "/clear":
                messages = [m for m in messages if m["role"] == "system"]
                if session_id:
                    mgr.clear_messages(session_id)
                print("(history cleared)")
                logger.info("History cleared")
                continue
            elif cmd == "/system":
                if not session_id:
                    print("(no active session, use --session <name> to start one)")
                    continue
                if len(parts) > 1:
                    new_sp = parts[1] if parts[1] != "clear" else None
                    mgr.update_session(session_id, system_prompt=new_sp)
                    print(f"System prompt: {'cleared' if new_sp is None else 'set'}")
                    logger.info(f"System prompt updated: {new_sp}")
                else:
                    s = mgr.get_session(session_id)
                    if s and s.system_prompt:
                        print(f"System prompt: {s.system_prompt}")
                    else:
                        print("(no system prompt set)")
                continue
            elif cmd == "/skills":
                if not session_id:
                    print("(no active session)")
                    continue

                sub_parts = text.split()

                if len(sub_parts) > 1:
                    action = sub_parts[1]
                    s = mgr.get_session(session_id)
                    current = [n.strip() for n in (s.skills.split(",") if s and s.skills else []) if n.strip()]

                    if action == "enable" and len(sub_parts) > 2:
                        name = sub_parts[2]
                        if name not in current:
                            current.append(name)
                        mgr.update_session(session_id, skills=",".join(current))
                        print(f"Skill enabled: {name}")
                        logger.info(f"Skill enabled: {name}, current_skills={current}")
                    elif action == "disable" and len(sub_parts) > 2:
                        name = sub_parts[2]
                        current = [n for n in current if n != name]
                        mgr.update_session(session_id, skills=",".join(current))
                        print(f"Skill disabled: {name}")
                        logger.info(f"Skill disabled: {name}, current_skills={current}")
                    elif action == "clear":
                        mgr.update_session(session_id, skills="")
                        print("All skills disabled")
                        logger.info("All skills cleared")
                    else:
                        print("Usage: /skills [enable|disable|clear] <name>")
                else:
                    s = mgr.get_session(session_id)
                    enabled = set(
                        n.strip() for n in (s.skills.split(",") if s and s.skills else []) if n.strip()
                    )
                    from skills import SkillLoader, default_skill_dirs
                    loader = SkillLoader(default_skill_dirs())
                    loader.load()
                    skills_list = [sk.to_dict() for sk in loader.list_skills()]
                    if not skills_list:
                        print("(no skills available)")
                    else:
                        for sk in skills_list:
                            mark = " [enabled]" if sk["name"] in enabled else ""
                            print(f"  {sk['name']}{mark}: {sk['description']}")
                    logger.info(f"Listed skills, enabled={enabled}")
                continue
            elif cmd == "/help":
                print("Commands:")
                print("  /exit, /quit   退出")
                print("  /clear         清除对话历史")
                print("  /sessions      列出所有会话")
                print("  /new <name>    创建新会话")
                print("  /system        查看/设置 system prompt")
                print("  /skills        管理 skills")
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
                logger.info(f"Switched to new session: {name}, id={session_id}")
                continue
            else:
                print(f"Unknown command: {cmd}")
                continue

        messages.append({"role": "user", "content": text})
        logger.info(f"User input: '{text}', messages count (local): {len(messages)}")

        try:
            extra_headers = {}
            if session_id:
                extra_headers["X-Session-Id"] = session_id
                request_messages = [{"role": "user", "content": text}]
                logger.info(f"Sending with session_id={session_id}, only new user message")
            else:
                request_messages = messages
                logger.info(f"Sending full messages (no session), count={len(request_messages)}")

            logger.debug(f"Request messages: {request_messages}")

            response = client.chat.completions.create(
                model=model,
                messages=request_messages,
                temperature=temperature,
                stream=False,
                extra_headers=extra_headers,
            )
            choices = getattr(response, "choices", None)
            if not choices:
                err_msg = f"[Error] Unexpected response: {response}"
                print(err_msg, file=sys.stderr)
                logger.error(err_msg)
                continue

            reply = choices[0].message.content or ""
            print(reply)
            messages.append({"role": "assistant", "content": reply})
            logger.debug(f"Full reply: {reply}")
            logger.info(f"Local messages count after turn: {len(messages)}")

        except Exception as e:
            err_msg = f"[Error] {e}"
            print(err_msg, file=sys.stderr)
            logger.exception(f"Exception during chat completion: {e}")

    logger.info("REPL loop ended")


def main():
    parser = argparse.ArgumentParser(description="Interactive chat with local model")
    parser.add_argument("--model", default="deepseek-chat", help="Model name (default: deepseek-chat)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--temperature", type=float, default=0.3, help="Sampling temperature (default: 0.3)")
    parser.add_argument("--system", help="Optional system prompt")
    parser.add_argument("--session", help="Session name (auto-create if not exists)")
    args = parser.parse_args()

    logger.info(f"Starting chat.py, model={args.model}, base_url={args.base_url}, session={args.session}")
    client = build_client(args.base_url)
    repl(client, args.model, args.system, args.temperature, args.session)


if __name__ == "__main__":
    main()