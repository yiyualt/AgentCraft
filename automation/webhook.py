"""Webhook trigger for external event invocation.

Allows external systems to trigger agent tasks via HTTP webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WebhookTrigger:
    """Webhook trigger configuration."""
    name: str
    url: str                   # Webhook URL path: /webhook/{name}
    secret: str | None = None  # Optional secret for signature validation
    enabled: bool = True
    agent_type: str = "general-purpose"
    timeout: int = 180
    delivery_mode: str = "none"

    def validate_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook signature using HMAC-SHA256."""
        if not self.secret:
            return True  # No secret configured, skip validation

        expected = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


class WebhookStore:
    """Store for webhook trigger configurations."""

    def __init__(self, config_path: str | None = None):
        from pathlib import Path
        self.config_path = Path(config_path or "~/.agentcraft/webhooks.json")
        self.config_path = self.config_path.expanduser()
        self._webhooks: dict[str, WebhookTrigger] = {}
        self._load()

    def _load(self) -> None:
        """Load webhook configurations."""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                for name, cfg in data.get("webhooks", {}).items():
                    self._webhooks[name] = WebhookTrigger(
                        name=name,
                        url=cfg.get("url", f"/webhook/{name}"),
                        secret=cfg.get("secret"),
                        enabled=cfg.get("enabled", True),
                        agent_type=cfg.get("agent_type", "general-purpose"),
                        timeout=cfg.get("timeout", 180),
                        delivery_mode=cfg.get("delivery_mode", "none"),
                    )
                logger.info(f"[Webhook] Loaded {len(self._webhooks)} webhooks")
            except Exception as e:
                logger.error(f"[Webhook] Failed to load config: {e}")

    def get_webhook(self, name: str) -> WebhookTrigger | None:
        """Get webhook by name."""
        return self._webhooks.get(name)

    def list_webhooks(self) -> list[WebhookTrigger]:
        """List all webhooks."""
        return list(self._webhooks.values())


@dataclass
class WebhookEvent:
    """Received webhook event."""
    webhook_name: str
    payload: dict[str, Any]
    headers: dict[str, str]
    received_at: float
    signature_valid: bool
    trigger_id: str              # Unique trigger ID


class WebhookExecutor:
    """Execute agent tasks triggered by webhooks."""

    def __init__(
        self,
        store: WebhookStore,
        agent_executor_factory: Any,
        event_store_path: str | None = None,
    ):
        self._store = store
        self._agent_executor_factory = agent_executor_factory
        self._event_store_path = event_store_path or "~/.agentcraft/webhook-events.json"
        self._events: list[WebhookEvent] = []

    async def handle_webhook(
        self,
        webhook_name: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes,
    ) -> dict[str, Any]:
        """Handle incoming webhook and trigger agent task.

        Args:
            webhook_name: Name of the webhook trigger
            payload: JSON payload from webhook
            headers: HTTP headers (including signature)
            raw_body: Raw request body for signature validation

        Returns:
            Execution result or error
        """
        webhook = self._store.get_webhook(webhook_name)
        if not webhook:
            logger.warning(f"[Webhook] Unknown webhook: {webhook_name}")
            return {"error": f"Unknown webhook: {webhook_name}", "status": "not_found"}

        if not webhook.enabled:
            logger.info(f"[Webhook] Webhook {webhook_name} is disabled")
            return {"error": f"Webhook disabled", "status": "disabled"}

        # Validate signature
        signature = headers.get("X-Webhook-Signature", "")
        signature_valid = webhook.validate_signature(raw_body, signature)

        if not signature_valid:
            logger.warning(f"[Webhook] Invalid signature for {webhook_name}")
            return {"error": "Invalid signature", "status": "signature_error"}

        # Create trigger ID
        trigger_id = f"trigger-{uuid.uuid4().hex[:8]}"
        received_at = time.time()

        # Record event
        event = WebhookEvent(
            webhook_name=webhook_name,
            payload=payload,
            headers=headers,
            received_at=received_at,
            signature_valid=signature_valid,
            trigger_id=trigger_id,
        )
        self._events.append(event)
        self._save_events()

        logger.info(f"[Webhook] Trigger {trigger_id} from {webhook_name}")

        # Extract task from payload
        task = payload.get("task") or payload.get("message") or ""
        if not task:
            # Try to generate task from payload
            task = self._generate_task_from_payload(webhook_name, payload)

        if not task:
            logger.warning(f"[Webhook] No task in payload for {webhook_name}")
            return {
                "error": "No task specified",
                "status": "invalid_payload",
                "trigger_id": trigger_id,
            }

        # Execute agent task
        try:
            executor = self._agent_executor_factory()
            result = await executor.run(
                task=task,
                agent_type=webhook.agent_type,
                timeout=webhook.timeout,
            )

            logger.info(f"[Webhook] Trigger {trigger_id} completed")

            return {
                "trigger_id": trigger_id,
                "webhook": webhook_name,
                "task": task[:100],
                "status": "ok",
                "result": result[:500],
                "elapsed": time.time() - received_at,
            }

        except Exception as e:
            logger.error(f"[Webhook] Trigger {trigger_id} failed: {e}")
            return {
                "trigger_id": trigger_id,
                "webhook": webhook_name,
                "status": "error",
                "error": str(e),
            }

    def _generate_task_from_payload(self, webhook_name: str, payload: dict[str, Any]) -> str:
        """Generate task description from payload."""
        # Common payload patterns
        if "action" in payload:
            return f"Handle {payload['action']} event from {webhook_name}"

        if "event_type" in payload:
            return f"Process {payload['event_type']} event"

        # GitHub webhook patterns
        if "repository" in payload and "pusher" in payload:
            repo = payload["repository"].get("full_name", "unknown")
            return f"Handle push to {repo}"

        # Generic
        return f"Process webhook event from {webhook_name}"

    def _save_events(self) -> None:
        """Save events to file."""
        from pathlib import Path
        path = Path(self._event_store_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Keep last 100 events
        events_to_save = self._events[-100:]
        data = {
            "events": [
                {
                    "webhook_name": e.webhook_name,
                    "trigger_id": e.trigger_id,
                    "received_at": e.received_at,
                    "signature_valid": e.signature_valid,
                    "payload": e.payload,
                }
                for e in events_to_save
            ]
        }
        path.write_text(json.dumps(data, indent=2))

    def get_recent_events(self, limit: int = 50) -> list[WebhookEvent]:
        """Get recent webhook events."""
        return self._events[-limit:]


# Global instances
_webhook_store: WebhookStore | None = None
_webhook_executor: WebhookExecutor | None = None


def get_webhook_store() -> WebhookStore | None:
    """Get global webhook store."""
    return _webhook_store


def get_webhook_executor() -> WebhookExecutor | None:
    """Get global webhook executor."""
    return _webhook_executor


def init_webhooks(agent_executor_factory: Any) -> None:
    """Initialize webhook system."""
    global _webhook_store, _webhook_executor
    _webhook_store = WebhookStore()
    _webhook_executor = WebhookExecutor(_webhook_store, agent_executor_factory)
    logger.info("[Webhook] System initialized")