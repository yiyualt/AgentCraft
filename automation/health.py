"""Cron health check and heartbeat mechanism.

Monitors scheduler health and job execution status.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from automation.store import CronStore
from automation.scheduler import get_scheduler
from automation.types import CronJobStatus

logger = logging.getLogger(__name__)


class CronHealthChecker:
    """Health checker for cron system.

    Checks:
    - Scheduler is running
    - Jobs are executing on schedule
    - No stuck jobs (running too long)
    - Database connectivity
    """

    def __init__(self, store: CronStore, max_run_time: float = 3600.0):
        """Initialize health checker.

        Args:
            store: CronStore instance
            max_run_time: Maximum allowed run time before considering stuck
        """
        self._store = store
        self._max_run_time = max_run_time
        self._last_check: float | None = None
        self._check_interval: float = 60.0  # Check every 60s

    async def check(self) -> dict[str, Any]:
        """Perform health check."""
        now = time.time()
        self._last_check = now

        issues: list[str] = []
        status: dict[str, Any] = {
            "timestamp": now,
            "healthy": True,
            "scheduler_running": False,
            "database_connected": False,
            "jobs": {},
            "stuck_jobs": [],
            "issues": [],
        }

        # Check scheduler
        scheduler = get_scheduler()
        if scheduler:
            status["scheduler_running"] = scheduler._scheduler.running if hasattr(scheduler, '_scheduler') else False
        else:
            issues.append("Scheduler not initialized")
            status["scheduler_running"] = False

        # Check database
        try:
            jobs_list = self._store.list_jobs()
            status["database_connected"] = True
            status["total_jobs"] = len(jobs_list)
        except Exception as e:
            status["database_connected"] = False
            issues.append(f"Database error: {e}")

        # Check jobs
        jobs = jobs_list if "jobs_list" in dir() else []
        for job in jobs:
            job_status = {
                "name": job.name,
                "enabled": job.enabled,
                "status": job.state.status.value,
                "last_run": job.state.last_run_at,
                "next_run": job.state.next_run_at,
            }
            status["jobs"][job.id] = job_status

            # Check for stuck jobs
            if job.state.status == CronJobStatus.RUNNING:
                if job.state.last_run_at:
                    running_time = now - job.state.last_run_at
                    if running_time > self._max_run_time:
                        status["stuck_jobs"].append({
                            "id": job.id,
                            "name": job.name,
                            "running_time": running_time,
                        })
                        issues.append(f"Job {job.id} stuck for {running_time:.0f}s")

        # Overall health
        if issues:
            status["healthy"] = False
        status["issues"] = issues

        return status

    async def run_heartbeat_loop(self) -> None:
        """Run continuous heartbeat check."""
        while True:
            await self.check()
            await asyncio.sleep(self._check_interval)

    def get_last_check(self) -> float | None:
        """Get timestamp of last check."""
        return self._last_check


class CronMonitor:
    """Monitor for cron execution events.

    Tracks:
    - Execution times
    - Success/failure rates
    - Error patterns
    """

    def __init__(self, store: CronStore):
        self._store = store
        self._events: list[dict[str, Any]] = []
        self._max_events: int = 1000

    def record_event(self, event: dict[str, Any]) -> None:
        """Record a cron event."""
        event["timestamp"] = time.time()
        self._events.append(event)

        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events."""
        return self._events[-limit:]

    def get_statistics(self, job_id: str | None = None) -> dict[str, Any]:
        """Get execution statistics."""
        runs = self._store.get_runs(job_id or "", limit=100) if job_id else []

        if not runs:
            return {"total_runs": 0}

        ok_count = sum(1 for r in runs if r["status"] == "ok")
        error_count = sum(1 for r in runs if r["status"] == "error")

        avg_duration = sum(r.get("duration_ms", 0) for r in runs) / len(runs) if runs else 0

        return {
            "total_runs": len(runs),
            "ok_runs": ok_count,
            "error_runs": error_count,
            "success_rate": ok_count / len(runs) if runs else 0,
            "avg_duration_ms": avg_duration,
            "last_run": runs[0] if runs else None,
        }


# Global instances
_health_checker: CronHealthChecker | None = None
_monitor: CronMonitor | None = None


def get_health_checker() -> CronHealthChecker | None:
    """Get global health checker."""
    return _health_checker


def get_monitor() -> CronMonitor | None:
    """Get global monitor."""
    return _monitor


def init_health_monitoring(store: CronStore) -> None:
    """Initialize health monitoring."""
    global _health_checker, _monitor
    _health_checker = CronHealthChecker(store)
    _monitor = CronMonitor(store)
    logger.info("[Cron] Health monitoring initialized")