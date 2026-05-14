"""Automation types - Cron schedule and job definitions."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Literal


# ===== Schedule Types =====

@dataclass
class AtSchedule:
    """One-time schedule at specific time."""
    at: str  # ISO datetime: "2024-01-01T10:00:00"
    kind: Literal["at"] = "at"


@dataclass
class EverySchedule:
    """Interval schedule."""
    every_ms: int  # milliseconds (3600000 = 1 hour)
    kind: Literal["every"] = "every"
    anchor_ms: int | None = None  # Optional anchor time


@dataclass
class CronExpressionSchedule:
    """Standard cron expression."""
    expr: str  # "0 9 * * *" (minute hour day month weekday)
    kind: Literal["cron"] = "cron"
    tz: str | None = None  # "Asia/Shanghai"
    stagger_ms: int | None = None  # Optional stagger window


# Union type
CronSchedule = AtSchedule | EverySchedule | CronExpressionSchedule


# ===== Delivery Types =====

class DeliveryMode(enum.Enum):
    """How to deliver job results."""
    NONE = "none"          # No delivery, just execute
    ANNOUNCE = "announce"  # Send to Channel (Telegram/CLI)
    WEBHOOK = "webhook"    # POST to external URL


@dataclass
class CronDelivery:
    """Delivery configuration."""
    mode: DeliveryMode = DeliveryMode.NONE
    channel: str | None = None     # Channel ID for announce
    to: str | None = None          # Destination (user/chat ID)
    webhook_url: str | None = None # Webhook URL
    thread_id: str | None = None   # Thread/topic ID
    account_id: str | None = None  # Multi-account support
    best_effort: bool = False      # Ignore delivery errors

    # Failure notification
    failure_channel: str | None = None
    failure_to: str | None = None


# ===== Job State =====

class CronJobStatus(enum.Enum):
    """Job execution status."""
    IDLE = "idle"          # Not yet run
    RUNNING = "running"    # Currently executing
    OK = "ok"              # Completed successfully
    ERROR = "error"        # Execution failed
    SKIPPED = "skipped"    # Skipped (disabled/conditions)
    DISABLED = "disabled"  # Manually disabled


class SessionTarget(enum.Enum):
    """Where to execute the job."""
    MAIN = "main"          # Main session
    ISOLATED = "isolated"  # New isolated session
    NEW = "new"            # Fresh session each run


@dataclass
class CronJobState:
    """Runtime state of a job."""
    status: CronJobStatus = CronJobStatus.IDLE
    last_run_at: float | None = None      # Timestamp
    next_run_at: float | None = None      # Timestamp
    last_result: str | None = None        # Result summary
    last_error: str | None = None         # Error message
    run_count: int = 0                    # Total runs
    error_count: int = 0                  # Total errors


# ===== Job Definition =====

@dataclass
class CronJob:
    """Complete cron job definition."""
    id: str                               # Unique job ID
    name: str                             # Human-readable name
    schedule: CronSchedule                # Schedule type
    task: str                             # Agent task description
    agent_type: str = "general-purpose"   # Agent type
    session_target: SessionTarget = SessionTarget.ISOLATED
    delivery: CronDelivery = field(default_factory=CronDelivery)
    state: CronJobState = field(default_factory=CronJobState)
    enabled: bool = True
    timeout: int = 180                    # Execution timeout
    max_retries: int = 0                  # Retry on failure
    created_at: float | None = None
    updated_at: float | None = None

    def is_active(self) -> bool:
        """Check if job should run."""
        return self.enabled and self.state.status != CronJobStatus.DISABLED

    def needs_run(self) -> bool:
        """Check if job needs to run now."""
        if not self.is_active():
            return False
        if self.state.status == CronJobStatus.RUNNING:
            return False
        return True


# ===== Telemetry =====

@dataclass
class CronRunTelemetry:
    """Telemetry for a job run."""
    job_id: str
    run_at: float
    duration_ms: int
    status: CronJobStatus
    model: str | None = None
    provider: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    error: str | None = None
    result: str | None = None


# ===== Helpers =====

def parse_schedule(schedule_dict: dict[str, Any]) -> CronSchedule:
    """Parse schedule from dict."""
    # Determine kind by presence of specific fields
    if "at" in schedule_dict:
        return AtSchedule(at=schedule_dict["at"])
    elif "every_ms" in schedule_dict:
        return EverySchedule(
            every_ms=schedule_dict["every_ms"],
            anchor_ms=schedule_dict.get("anchor_ms"),
        )
    elif "expr" in schedule_dict:
        return CronExpressionSchedule(
            expr=schedule_dict["expr"],
            tz=schedule_dict.get("tz"),
            stagger_ms=schedule_dict.get("stagger_ms"),
        )
    else:
        raise ValueError(f"Unknown schedule format: {schedule_dict}")


def schedule_to_dict(schedule: CronSchedule) -> dict[str, Any]:
    """Convert schedule to dict."""
    return {
        "kind": schedule.kind,
        **{k: v for k, v in schedule.__dict__.items() if k != "kind" and v is not None}
    }