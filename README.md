# xiaoke-actions

`xiaoke-actions` is a small MCP server for actions Xiaoke can take toward the outside world.

Version 1 intentionally exposes only one tool:

- `send_note(message, title?, urgency?)` sends a note to Xiaomao's phone through ntfy.

The server does not decide when Xiaoke should send a note. It only delivers the action with guardrails: length limits, rate limiting, duplicate suppression, quiet hours, and structured logs.

## Environment

Required:

- `NTFY_TOPIC` or `NTFY_URL`

Optional:

- `NTFY_TOKEN`
- `DEFAULT_TITLE` default: `小克`
- `MAX_MESSAGE_CHARS` default: `500`
- `RATE_LIMIT_PER_HOUR` default: `6`
- `MIN_INTERVAL_SECONDS` default: `30`
- `DEDUPE_WINDOW_SECONDS` default: `300`
- `QUIET_HOURS` example: `23:30-08:00`
- `QUIET_MODE` one of `suppress`, `downgrade`, `allow`; default: `suppress`
- `TIMEZONE` default: `Asia/Shanghai`
- `MCP_PATH` default: `/mcp`
- `PORT` default: `8000`

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:NTFY_TOPIC="your-ntfy-topic"
.\.venv\Scripts\python -m xiaoke_actions.server
```

The MCP endpoint is:

```text
http://localhost:8000/mcp
```

## Render

Create a new Web Service and point it at this folder.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
python -m xiaoke_actions.server
```

Set `NTFY_TOPIC` or `NTFY_URL` in Render environment variables.
