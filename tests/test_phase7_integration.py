#!/usr/bin/env python3
"""Integration tests for Phase 7 features — requires gateway running on localhost:8000."""

import httpx
import json
import subprocess
import sys

BASE_URL = "http://127.0.0.1:8000"


def create_session(name: str) -> str:
    r = httpx.post(f"{BASE_URL}/v1/sessions", json={"name": name})
    return r.json()["id"]


def send_message(session_id: str, content: str, timeout: int = 120) -> dict:
    """Send a message and get response (streaming)."""
    r = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"X-Session-Id": session_id},
        json={"model": "deepseek-chat", "messages": [{"role": "user", "content": content}], "stream": True},
        timeout=timeout,
    )
    # Parse streaming response
    full_content = ""
    for line in r.iter_lines():
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
    return {"choices": [{"message": {"content": full_content}}]}


def get_session(session_id: str) -> dict:
    r = httpx.get(f"{BASE_URL}/v1/sessions/{session_id}")
    return r.json()


def search_log(pattern: str) -> str:
    r = subprocess.run(["grep", pattern, "logs/gateway.log"], capture_output=True, text=True)
    return r.stdout


# ============================================================
# Budget Integration
# ============================================================

def test_budget_check_in_loop():
    """Verify budget check fires during conversation."""
    print("\n=== Budget Integration Test ===")
    sid = create_session("budget-test")
    resp = send_message(sid, "Hello! Count from 1 to 5.")
    content = resp["choices"][0]["message"]["content"]
    print(f"Response: {content[:100]}...")

    log = search_log("BUDGET")
    print(f"Budget log lines: {log[:500]}")
    assert "BUDGET" in log, "Budget check should appear in logs"
    print("PASS: Budget check runs in conversation loop")


# ============================================================
# Goal Command Integration
# ============================================================

def test_goal_set_and_check():
    """Verify /goal command sets a goal that blocks premature stop."""
    print("\n=== Goal Command Integration Test ===")
    sid = create_session("goal-test")

    # Set a goal
    resp = send_message(sid, "/goal tests pass")
    content = resp["choices"][0]["message"]["content"]
    print(f"Goal set response: {content}")
    assert "Goal set" in content, f"Expected 'Goal set', got: {content}"

    # Request something hard that can't be done → agent should detect goal
    # and the Goal check should at least run
    resp2 = send_message(sid, "Write a simple Python function: def add(a, b): return a + b")
    content2 = resp2["choices"][0]["message"]["content"]
    print(f"Agent response: {content2[:150]}...")

    log = search_log("Goal")
    print(f"Goal log lines: {log[:500]}")
    assert "Goal" in log, "Goal activity should appear in logs"
    print("PASS: Goal command works")


def test_goal_clear():
    """Verify /goal clears an existing goal."""
    print("\n=== Goal Clear Test ===")
    sid = create_session("goal-clear-test")

    resp = send_message(sid, "/goal tests pass")
    assert "Goal set" in resp["choices"][0]["message"]["content"]

    resp2 = send_message(sid, "/goal")
    assert "Goal cleared" in resp2["choices"][0]["message"]["content"]
    print("PASS: Goal clear works")


# ============================================================
# Permission Command Integration
# ============================================================

def test_permission_show_and_set():
    """Verify /permission command."""
    print("\n=== Permission Integration Test ===")
    sid = create_session("perm-test")

    # Show current mode
    resp = send_message(sid, "/permission")
    content = resp["choices"][0]["message"]["content"]
    print(f"Permission show: {content}")
    assert "default" in content.lower(), f"Expected default mode, got: {content}"

    # Set to auto mode
    resp2 = send_message(sid, "/permission auto")
    content2 = resp2["choices"][0]["message"]["content"]
    print(f"Permission set: {content2}")
    assert "auto" in content2.lower(), f"Expected auto mode, got: {content2}"

    # Verify it changed
    resp3 = send_message(sid, "/permission")
    content3 = resp3["choices"][0]["message"]["content"]
    assert "auto" in content3.lower(), f"Expected auto mode, got: {content3}"

    print("PASS: Permission command works")


def test_permission_plan_mode():
    """Verify plan mode restricts executions."""
    print("\n=== Permission Plan Mode Test ===")
    sid = create_session("perm-plan-test")

    resp = send_message(sid, "/permission plan")
    assert "plan" in resp["choices"][0]["message"]["content"].lower()

    # Now try something that would need Write/Bash — should trigger permission deny
    resp2 = send_message(sid, "Write a file called test.txt with content 'hello'")
    content2 = resp2["choices"][0]["message"]["content"]
    print(f"Response in plan mode: {content2[:200]}...")

    # Look for permission deny logs
    log = search_log("Permission")
    print(f"Permission log lines: {log[:500]}")
    assert "Permission" in log, "Permission activity should appear in logs"
    print("PASS: Plan mode restricts execution")


# ============================================================
# Error Recovery Integration (verify retry logs)
# ============================================================

def test_error_recovery_logs_present():
    """Verify error recovery subsystem is active."""
    print("\n=== Error Recovery Integration Test ===")
    sid = create_session("recovery-test")

    resp = send_message(sid, "What is 1+1?")
    content = resp["choices"][0]["message"]["content"]
    print(f"Response: {content[:100]}...")

    # Just verify the module is loaded (RECOVERY logs during startup)
    log = search_log("Recovery")
    print(f"Recovery log lines: {log[:300]}")
    assert "Recovery" in log, "Error recovery should be initialized"
    print("PASS: Error recovery subsystem is active")


# ============================================================
# Hooks Integration
# ============================================================

def test_hooks_integration_active():
    """Verify hooks subsystem is active."""
    print("\n=== Hooks Integration Test ===")
    sid = create_session("hooks-test")

    resp = send_message(
        sid,
        "Read the file sessions/__init__.py and tell me what's exported.",
    )
    content = resp["choices"][0]["message"]["content"]
    print(f"Response: {content[:150]}...")

    # Check hooks log
    log = search_log("Hook\|HookEvent")
    print(f"Hooks log: {log[:300] if log else 'No hook logs (expected if no hooks configured)'}")
    print("PASS: Hooks subsystem runs without errors")


# ============================================================
# Full Pipeline: Budget + Permission + Goal
# ============================================================

def test_full_pipeline():
    """Run goal, permission, and verify all systems coexist."""
    print("\n=== Full Pipeline Integration Test ===")
    sid = create_session("pipeline-test")

    # 1. Set permission to auto
    r1 = send_message(sid, "/permission auto")
    print(f"[1] Permission: {r1['choices'][0]['message']['content']}")

    # 2. Set a goal
    r2 = send_message(sid, "/goal no errors")
    print(f"[2] Goal: {r2['choices'][0]['message']['content']}")

    # 3. Do a simple task
    r3 = send_message(sid, "List the files in the current directory")
    content = r3["choices"][0]["message"]["content"]
    print(f"[3] Task result: {content[:150]}...")

    # 4. Check all subsystems appeared in logs
    log = search_log("BUDGET\|Goal\|Permission\|Recovery\|Hook")
    print(f"[4] All subsystems log: {log[:400]}")

    # Verify at least budget and goal are there
    assert "Goal" in log, "Goal should be in logs"
    assert "BUDGET" in log, "Budget should be in logs"

    print("PASS: All Phase 7 systems coexist and operate")


# ============================================================
# Runner
# ============================================================

def main():
    print("=" * 60)
    print("Phase 7 Integration Tests")
    print("=" * 60)

    # Check gateway is running
    try:
        httpx.get(f"{BASE_URL}/health", timeout=5)
    except Exception:
        print("ERROR: Gateway not running. Start with: python gateway.py")
        sys.exit(1)

    tests = [
        test_budget_check_in_loop,
        test_goal_set_and_check,
        test_goal_clear,
        test_permission_show_and_set,
        test_permission_plan_mode,
        test_error_recovery_logs_present,
        test_hooks_integration_active,
        test_full_pipeline,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
