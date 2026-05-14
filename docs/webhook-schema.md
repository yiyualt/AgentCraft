# Webhook Payload Schema

## Overview

Webhooks allow external systems to trigger agent tasks via HTTP POST requests.

## Endpoint

```
POST /webhook/{webhook_name}
```

## Headers

| Header | Required | Description |
|--------|----------|-------------|
| Content-Type | Yes | Must be `application/json` |
| X-Webhook-Signature | Optional | HMAC-SHA256 signature if secret configured |

## Signature Validation

If webhook has a secret configured, signature must be provided:

```python
import hmac
import hashlib

signature = hmac.new(
    secret.encode(),
    json_payload.encode(),
    hashlib.sha256
).hexdigest()

headers = {"X-Webhook-Signature": signature}
```

## Payload Schema

### Basic Payload

```json
{
  "task": "Analyze the data and generate a report"
}
```

### Alternative Field Names

```json
{
  "message": "Check the latest commits and summarize changes"
}
```

### GitHub Webhook Example

```json
{
  "ref": "refs/heads/main",
  "repository": {
    "id": 123456,
    "name": "agentcraft",
    "full_name": "pyleaf/agentcraft",
    "html_url": "https://github.com/pyleaf/agentcraft"
  },
  "pusher": {
    "name": "username",
    "email": "user@example.com"
  },
  "commits": [
    {
      "id": "abc123",
      "message": "Add new feature",
      "author": {"name": "username"}
    }
  ]
}
```

If no `task` field is provided, task is auto-generated from payload:
- GitHub push → "Handle push to {repo_name}"
- Event with `action` → "Handle {action} event from {webhook_name}"
- Event with `event_type` → "Process {event_type} event"

### Custom Payload Fields

Any additional fields are passed to the agent:

```json
{
  "task": "Generate report",
  "report_type": "daily",
  "format": "markdown",
  "recipients": ["team@example.com"]
}
```

## Response Schema

### Success Response

```json
{
  "trigger_id": "trigger-abc123",
  "webhook": "github-push",
  "task": "Handle push to pyleaf/agentcraft",
  "status": "ok",
  "result": "Task completed successfully...",
  "elapsed": 5.2
}
```

### Error Responses

**404 - Webhook Not Found**
```json
{
  "detail": "Unknown webhook: my-webhook"
}
```

**401 - Invalid Signature**
```json
{
  "detail": "Invalid signature"
}
```

**403 - Webhook Disabled**
```json
{
  "detail": "Webhook disabled"
}
```

**400 - Invalid Payload**
```json
{
  "detail": "Invalid JSON payload"
}
```

## Webhook Configuration

Webhooks are configured in `~/.agentcraft/webhooks.json`:

```json
{
  "webhooks": {
    "github-push": {
      "url": "/webhook/github-push",
      "secret": "your-secret-key",
      "enabled": true,
      "agent_type": "general-purpose",
      "timeout": 180,
      "delivery_mode": "none"
    },
    "slack-command": {
      "url": "/webhook/slack",
      "secret": null,
      "enabled": true,
      "agent_type": "explore",
      "timeout": 60
    }
  }
}
```

## Example Usage

### curl

```bash
curl -X POST http://localhost:8000/webhook/github-push \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: abc123..." \
  -d '{"task": "Check latest commits"}'
```

### Python

```python
import httpx
import hmac
import hashlib
import json

webhook_name = "github-push"
secret = "your-secret"
payload = {"task": "Analyze repository changes"}

signature = hmac.new(
    secret.encode(),
    json.dumps(payload).encode(),
    hashlib.sha256
).hexdigest()

response = httpx.post(
    f"http://localhost:8000/webhook/{webhook_name}",
    json=payload,
    headers={
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    }
)

print(response.json())
```

### GitHub Actions

```yaml
name: Trigger Agent
on: push

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Send webhook
        run: |
          curl -X POST $WEBHOOK_URL \
            -H "Content-Type: application/json" \
            -H "X-Webhook-Signature: $SIGNATURE" \
            -d '{"task": "Review this push"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/{name}` | POST | Trigger webhook |
| `/webhooks` | GET | List all webhooks |
| `/webhooks/events` | GET | Get recent events |