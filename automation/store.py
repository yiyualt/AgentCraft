"""CronStore - Persistent storage for cron jobs.

Uses SQLite for durability and state tracking.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from automation.types import (
    CronJob,
    CronJobState,
    CronJobStatus,
    CronSchedule,
    CronDelivery,
    DeliveryMode,
    SessionTarget,
    parse_schedule,
    schedule_to_dict,
)

logger = logging.getLogger(__name__)


def _default_cron_dir() -> Path:
    """Get default cron storage directory."""
    return Path.home() / ".agentcraft" / "cron"


class CronStore:
    """SQLite-based persistent store for cron jobs.

    Stores:
    - Job definitions (schedule, task, delivery)
    - Job state (status, last run, errors)
    - Run history (telemetry)
    """

    def __init__(self, db_path: str | None = None):
        """Initialize store.

        Args:
            db_path: Optional custom path, defaults to ~/.agentcraft/cron/jobs.db
        """
        self.db_path = Path(db_path) if db_path else _default_cron_dir() / "jobs.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        # Jobs table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                schedule_json TEXT NOT NULL,
                task TEXT NOT NULL,
                agent_type TEXT DEFAULT 'general-purpose',
                session_target TEXT DEFAULT 'isolated',
                delivery_json TEXT,
                timeout INTEGER DEFAULT 180,
                max_retries INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL,

                -- State fields
                status TEXT DEFAULT 'idle',
                last_run_at REAL,
                next_run_at REAL,
                last_result TEXT,
                last_error TEXT,
                run_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        """)

        # Run history table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                run_at REAL NOT NULL,
                duration_ms INTEGER,
                status TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                error TEXT,
                result TEXT,
                FOREIGN KEY (job_id) REFERENCES cron_jobs(id)
            )
        """)

        # Create index for fast lookups
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cron_runs_job_id ON cron_runs(job_id)
        """)

        self._conn.commit()
        logger.info(f"[CronStore] Initialized at {self.db_path}")

    # ===== CRUD Operations =====

    def create_job(self, job: CronJob) -> CronJob:
        """Create a new job."""
        now = time.time()
        job.created_at = now
        job.updated_at = now

        self._conn.execute("""
            INSERT INTO cron_jobs (
                id, name, enabled, schedule_json, task, agent_type,
                session_target, delivery_json, timeout, max_retries,
                created_at, updated_at, status, run_count, error_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id,
            job.name,
            1 if job.enabled else 0,
            json.dumps(schedule_to_dict(job.schedule)),
            job.task,
            job.agent_type,
            job.session_target.value,
            json.dumps(self._delivery_to_dict(job.delivery)),
            job.timeout,
            job.max_retries,
            job.created_at,
            job.updated_at,
            job.state.status.value,
            job.state.run_count,
            job.state.error_count,
        ))
        self._conn.commit()
        logger.info(f"[CronStore] Created job {job.id}: {job.name}")
        return job

    def get_job(self, job_id: str) -> CronJob | None:
        """Get job by ID."""
        row = self._conn.execute(
            "SELECT * FROM cron_jobs WHERE id=?", (job_id,)
        ).fetchone()

        if row:
            return self._row_to_job(row)
        return None

    def list_jobs(self, enabled_only: bool = False) -> list[CronJob]:
        """List all jobs."""
        if enabled_only:
            rows = self._conn.execute(
                "SELECT * FROM cron_jobs WHERE enabled=1"
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM cron_jobs").fetchall()

        return [self._row_to_job(row) for row in rows]

    def update_job(self, job: CronJob) -> CronJob:
        """Update job definition."""
        job.updated_at = time.time()

        self._conn.execute("""
            UPDATE cron_jobs SET
                name=?, enabled=?, schedule_json=?, task=?, agent_type=?,
                session_target=?, delivery_json=?, timeout=?, max_retries=?,
                updated_at=?, status=?, last_run_at=?, next_run_at=?,
                last_result=?, last_error=?, run_count=?, error_count=?
            WHERE id=?
        """, (
            job.name,
            1 if job.enabled else 0,
            json.dumps(schedule_to_dict(job.schedule)),
            job.task,
            job.agent_type,
            job.session_target.value,
            json.dumps(self._delivery_to_dict(job.delivery)),
            job.timeout,
            job.max_retries,
            job.updated_at,
            job.state.status.value,
            job.state.last_run_at,
            job.state.next_run_at,
            job.state.last_result,
            job.state.last_error,
            job.state.run_count,
            job.state.error_count,
            job.id,
        ))
        self._conn.commit()
        logger.info(f"[CronStore] Updated job {job.id}")
        return job

    def delete_job(self, job_id: str) -> bool:
        """Delete job."""
        cursor = self._conn.execute("DELETE FROM cron_jobs WHERE id=?", (job_id,))
        self._conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"[CronStore] Deleted job {job_id}")
        return deleted

    def update_state(self, job_id: str, state: CronJobState) -> None:
        """Update job state only."""
        self._conn.execute("""
            UPDATE cron_jobs SET
                status=?, last_run_at=?, next_run_at=?,
                last_result=?, last_error=?, run_count=?, error_count=?
            WHERE id=?
        """, (
            state.status.value,
            state.last_run_at,
            state.next_run_at,
            state.last_result,
            state.last_error,
            state.run_count,
            state.error_count,
            job_id,
        ))
        self._conn.commit()

    # ===== Run History =====

    def record_run(self, telemetry: dict[str, Any]) -> None:
        """Record a job run in history."""
        import uuid
        run_id = f"run-{uuid.uuid4().hex[:8]}"

        self._conn.execute("""
            INSERT INTO cron_runs (
                id, job_id, run_at, duration_ms, status,
                model, provider, input_tokens, output_tokens, total_tokens,
                error, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            telemetry["job_id"],
            telemetry["run_at"],
            telemetry.get("duration_ms"),
            telemetry["status"],
            telemetry.get("model"),
            telemetry.get("provider"),
            telemetry.get("input_tokens"),
            telemetry.get("output_tokens"),
            telemetry.get("total_tokens"),
            telemetry.get("error"),
            telemetry.get("result"),
        ))
        self._conn.commit()

    def get_runs(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get run history for a job."""
        rows = self._conn.execute("""
            SELECT * FROM cron_runs WHERE job_id=? ORDER BY run_at DESC LIMIT ?
        """, (job_id, limit)).fetchall()

        return [dict(row) for row in rows]

    # ===== Helpers =====

    def _row_to_job(self, row: sqlite3.Row) -> CronJob:
        """Convert database row to CronJob."""
        schedule = parse_schedule(json.loads(row["schedule_json"]))
        delivery = self._dict_to_delivery(json.loads(row["delivery_json"]) if row["delivery_json"] else {})

        state = CronJobState(
            status=CronJobStatus(row["status"]),
            last_run_at=row["last_run_at"],
            next_run_at=row["next_run_at"],
            last_result=row["last_result"],
            last_error=row["last_error"],
            run_count=row["run_count"],
            error_count=row["error_count"],
        )

        return CronJob(
            id=row["id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            schedule=schedule,
            task=row["task"],
            agent_type=row["agent_type"],
            session_target=SessionTarget(row["session_target"]),
            delivery=delivery,
            state=state,
            timeout=row["timeout"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _delivery_to_dict(self, delivery: CronDelivery) -> dict[str, Any]:
        """Convert delivery to dict."""
        return {
            "mode": delivery.mode.value,
            "channel": delivery.channel,
            "to": delivery.to,
            "webhook_url": delivery.webhook_url,
            "thread_id": delivery.thread_id,
            "account_id": delivery.account_id,
            "best_effort": delivery.best_effort,
            "failure_channel": delivery.failure_channel,
            "failure_to": delivery.failure_to,
        }

    def _dict_to_delivery(self, d: dict[str, Any]) -> CronDelivery:
        """Convert dict to delivery."""
        return CronDelivery(
            mode=DeliveryMode(d.get("mode", "none")),
            channel=d.get("channel"),
            to=d.get("to"),
            webhook_url=d.get("webhook_url"),
            thread_id=d.get("thread_id"),
            account_id=d.get("account_id"),
            best_effort=d.get("best_effort", False),
            failure_channel=d.get("failure_channel"),
            failure_to=d.get("failure_to"),
        )

    def close(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None