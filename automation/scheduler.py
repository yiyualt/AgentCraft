"""CronScheduler - Execute scheduled agent tasks.

Uses APScheduler for scheduling, integrates with AgentExecutor for execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from automation.store import CronStore
from automation.types import (
    CronJob,
    CronJobStatus,
    CronSchedule,
    AtSchedule,
    EverySchedule,
    CronExpressionSchedule,
    CronDelivery,
    DeliveryMode,
    SessionTarget,
)

logger = logging.getLogger(__name__)


class CronScheduler:
    """Scheduler that executes agent tasks on schedule.

    Features:
    - Three schedule types: at, every, cron expression
    - SQLite persistence via CronStore
    - Execution in isolated agent environment
    - Delivery: none, announce (channel), webhook
    """

    def __init__(
        self,
        store: CronStore,
        agent_executor_factory: Callable[[], Any] | None = None,
        delivery_handler: Callable[[str, str, str], None] | None = None,
    ):
        """Initialize scheduler.

        Args:
            store: CronStore for persistence
            agent_executor_factory: Factory to create AgentExecutor for each run
            delivery_handler: Handler for delivery (channel_id, message, error)
        """
        self._store = store
        self._agent_executor_factory = agent_executor_factory
        self._delivery_handler = delivery_handler
        self._scheduler = AsyncIOScheduler()
        self._running_jobs: dict[str, asyncio.Task] = {}

        logger.info("[CronScheduler] Initialized")

    def start(self) -> None:
        """Start the scheduler."""
        # Load existing jobs and schedule them
        jobs = self._store.list_jobs(enabled_only=True)
        for job in jobs:
            self._schedule_job(job)

        self._scheduler.start()
        logger.info(f"[CronScheduler] Started with {len(jobs)} jobs")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=False)

        # Cancel running tasks
        for task in self._running_jobs.values():
            task.cancel()

        logger.info("[CronScheduler] Stopped")

    # ===== Job Management =====

    def add_job(self, job: CronJob) -> CronJob:
        """Add and schedule a new job."""
        # Store in database
        created = self._store.create_job(job)

        # Schedule if enabled
        if job.enabled:
            self._schedule_job(created)

        return created

    def update_job(self, job: CronJob) -> CronJob:
        """Update job definition."""
        # Remove old schedule
        self._unschedule_job(job.id)

        # Update in database
        updated = self._store.update_job(job)

        # Reschedule if enabled
        if job.enabled:
            self._schedule_job(updated)

        return updated

    def delete_job(self, job_id: str) -> bool:
        """Delete job."""
        self._unschedule_job(job_id)
        return self._store.delete_job(job_id)

    def enable_job(self, job_id: str) -> bool:
        """Enable a job."""
        job = self._store.get_job(job_id)
        if job:
            job.enabled = True
            self._schedule_job(self._store.update_job(job))
            return True
        return False

    def disable_job(self, job_id: str) -> bool:
        """Disable a job."""
        job = self._store.get_job(job_id)
        if job:
            job.enabled = False
            job.state.status = CronJobStatus.DISABLED
            self._unschedule_job(job_id)
            self._store.update_job(job)
            return True
        return False

    def list_jobs(self) -> list[CronJob]:
        """List all jobs."""
        return self._store.list_jobs()

    def get_job(self, job_id: str) -> CronJob | None:
        """Get job by ID."""
        return self._store.get_job(job_id)

    # ===== Scheduling =====

    def _schedule_job(self, job: CronJob) -> None:
        """Schedule a job with APScheduler."""
        trigger = self._create_trigger(job.schedule)

        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            name=job.name,
            misfire_grace_time=60,  # Allow 60s grace for missed runs
        )

        # Update next_run_at
        scheduled_job = self._scheduler.get_job(job.id)
        if scheduled_job and hasattr(scheduled_job, 'next_run_time') and scheduled_job.next_run_time:
            job.state.next_run_at = scheduled_job.next_run_time.timestamp()
            self._store.update_state(job.id, job.state)

        logger.info(f"[CronScheduler] Scheduled job {job.id}: {job.schedule.kind}")

    def _unschedule_job(self, job_id: str) -> None:
        """Remove job from scheduler."""
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass  # Job may not exist

    def _create_trigger(self, schedule: CronSchedule):
        """Create APScheduler trigger from schedule."""
        if isinstance(schedule, AtSchedule):
            # One-time at specific datetime
            dt = datetime.fromisoformat(schedule.at)
            return DateTrigger(run_date=dt)

        elif isinstance(schedule, EverySchedule):
            # Interval
            seconds = schedule.every_ms / 1000
            return IntervalTrigger(seconds=seconds)

        elif isinstance(schedule, CronExpressionSchedule):
            # Cron expression
            return CronTrigger.from_crontab(
                schedule.expr,
                timezone=schedule.tz or "UTC",
            )

        else:
            raise ValueError(f"Unknown schedule type: {schedule}")

    # ===== Execution =====

    async def _execute_job(self, job_id: str) -> None:
        """Execute a scheduled job."""
        job = self._store.get_job(job_id)
        if not job:
            logger.error(f"[CronScheduler] Job {job_id} not found")
            return

        if not job.enabled:
            logger.info(f"[CronScheduler] Job {job_id} is disabled, skipping")
            return

        # Mark as running
        job.state.status = CronJobStatus.RUNNING
        job.state.last_run_at = time.time()
        self._store.update_state(job_id, job.state)

        start_time = time.time()
        telemetry: dict[str, Any] = {
            "job_id": job_id,
            "run_at": start_time,
            "status": CronJobStatus.OK.value,
        }

        try:
            logger.info(f"[CronScheduler] Executing job {job_id}: {job.task[:50]}...")

            # Execute agent task
            result = await self._run_agent_task(job)

            # Success
            job.state.status = CronJobStatus.OK
            job.state.last_result = result[:500] if result else None
            job.state.run_count += 1
            telemetry["status"] = CronJobStatus.OK.value
            telemetry["result"] = result[:500] if result else None

            # Handle delivery
            if job.delivery.mode != DeliveryMode.NONE:
                self._deliver_result(job, result)

        except asyncio.TimeoutError:
            job.state.status = CronJobStatus.ERROR
            job.state.last_error = f"Timeout after {job.timeout}s"
            job.state.error_count += 1
            telemetry["status"] = CronJobStatus.ERROR.value
            telemetry["error"] = f"Timeout after {job.timeout}s"

            # Failure notification
            if job.delivery.failure_channel:
                self._deliver_failure(job, f"Timeout after {job.timeout}s")

        except Exception as e:
            job.state.status = CronJobStatus.ERROR
            job.state.last_error = str(e)[:200]
            job.state.error_count += 1
            telemetry["status"] = CronJobStatus.ERROR.value
            telemetry["error"] = str(e)[:200]

            logger.error(f"[CronScheduler] Job {job_id} failed: {e}")

            # Failure notification
            if job.delivery.failure_channel:
                self._deliver_failure(job, str(e)[:200])

        finally:
            # Calculate duration
            telemetry["duration_ms"] = int((time.time() - start_time) * 1000)

            # Update next_run_at
            try:
                scheduled_job = self._scheduler.get_job(job_id)
                if scheduled_job and scheduled_job.next_run_time:
                    job.state.next_run_at = scheduled_job.next_run_time.timestamp()
            except Exception:
                job.state.next_run_at = None

            # Save state
            self._store.update_state(job_id, job.state)

            # Record run history
            self._store.record_run(telemetry)

            logger.info(f"[CronScheduler] Job {job_id} completed: {job.state.status.value}")

    async def _run_agent_task(self, job: CronJob) -> str:
        """Run agent task for job."""
        if not self._agent_executor_factory:
            return "[Error] AgentExecutor factory not configured"

        executor = self._agent_executor_factory()

        # Run in isolated environment (fresh session)
        result = await executor.run(
            task=job.task,
            agent_type=job.agent_type,
            timeout=job.timeout,
            fork_context=None,  # No fork context for cron jobs
            is_fork_child=False,
        )

        return result

    # ===== Delivery =====

    def _deliver_result(self, job: CronJob, result: str) -> None:
        """Deliver result via configured channel."""
        if not self._delivery_handler:
            logger.warning("[CronScheduler] Delivery handler not configured")
            return

        try:
            message = f"[Cron: {job.name}] Result:\n{result[:500]}"
            self._delivery_handler(job.delivery.channel, message, None)
            logger.info(f"[CronScheduler] Delivered result to {job.delivery.channel}")
        except Exception as e:
            logger.error(f"[CronScheduler] Delivery failed: {e}")

    def _deliver_failure(self, job: CronJob, error: str) -> None:
        """Deliver failure notification."""
        if not self._delivery_handler:
            return

        try:
            message = f"[Cron: {job.name}] ERROR:\n{error}"
            self._delivery_handler(job.delivery.failure_channel, message, error)
        except Exception as e:
            logger.error(f"[CronScheduler] Failure delivery failed: {e}")

    # ===== Status =====

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status."""
        jobs = self.list_jobs()
        running = sum(1 for j in jobs if j.state.status == CronJobStatus.RUNNING)
        ok = sum(1 for j in jobs if j.state.status == CronJobStatus.OK)
        error = sum(1 for j in jobs if j.state.status == CronJobStatus.ERROR)

        return {
            "scheduler_running": self._scheduler.running,
            "total_jobs": len(jobs),
            "enabled_jobs": sum(1 for j in jobs if j.enabled),
            "running": running,
            "ok": ok,
            "error": error,
            "jobs": {
                j.id: {
                    "name": j.name,
                    "status": j.state.status.value,
                    "next_run": j.state.next_run_at,
                    "last_run": j.state.last_run_at,
                }
                for j in jobs
            },
        }


# Module-level scheduler instance
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler | None:
    """Get global scheduler instance."""
    return _scheduler


def set_scheduler(scheduler: CronScheduler) -> None:
    """Set global scheduler instance."""
    global _scheduler
    _scheduler = scheduler