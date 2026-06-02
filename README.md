# xiaoke-actions

`xiaoke-actions` is a small MCP server for actions Xiaoke can take toward the outside world.

Version 1 intentionally exposes only one tool:

- `send_note(message, title?, urgency?, category?, intent?)` sends a note to Xiaomao's phone through ntfy.

The server does not decide when Xiaoke should send a note. It only delivers the action with guardrails: length limits, rate limiting, duplicate suppression, quiet hours, and structured logs.

`xiaoke-actions` stays an action outlet. Category and intent are metadata for routing, auditing, and future debugging; they are not decision logic.

## Tool

```text
send_note(
  message: str,
  title: str | None = None,
  urgency: str | None = "normal",
  category: str | None = "presence",
  intent: str | None = None
)
```

Allowed `urgency` values:

- `low`
- `normal`
- `high`
- `urgent`

Invalid urgency values are downgraded to `normal`.

Allowed `category` values:

- `presence`: everyday presence, companionship, wanting to say something
- `monitor`: phone state, environment state, behavior pattern reminders
- `task`: task or feature execution results
- `memory`: memory-related prompts or reflection results
- `system`: wake, error, maintenance, or debugging information

Invalid or empty category values are downgraded to `presence`.

`intent` is an optional short freeform purpose tag. It is whitespace-normalized and limited to 48 characters.

Examples:

```text
send_note(
  message="突然想给你递一张纸条。",
  category="presence",
  intent="affection"
)
```

```text
send_note(
  message="手机已经空闲一段时间了，要不要休息一下？",
  category="monitor",
  intent="phone_idle"
)
```

```text
send_note(
  message="自唤醒流程遇到错误，我已经记录下来等待排查。",
  category="system",
  intent="wake_error"
)
```

```text
send_note(
  message="我整理了一条关于今天状态的记忆。",
  category="memory",
  intent="reflection"
)
```

## Environment

Required:

- `NTFY_TOPIC` or `NTFY_URL`

Optional:

- `NTFY_TOKEN`
- `DEFAULT_TITLE` default: `Claude`
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

## SVAKOM Toy Bridge

Toy commands are queued by the Render MCP server into the Supabase
`action_queue` table. The Bluetooth side runs only on the local Windows
machine, so the local bridge must be open before Xiaoke can execute queued toy
commands.

Current chain:

- Render MCP tools enqueue `toy_main`, `toy_vibe`, `toy_stop`, or
  `toy_sequence`.
- Supabase stores those records with `domain = toy`.
- `start_toy_bridge.bat` starts the local bridge and polls the queue.
- The bridge claims one pending command, sends the BLE command through
  `bleak`, and marks the record `done` or `error`.

Local usage:

1. Run `start_toy_bridge.bat` from this folder and keep the visible window open.
2. Run `stop_toy_bridge.bat` or close the bridge window to stop it.
3. If Windows shows a stale pid or the bridge is not running, run
   `stop_toy_bridge.bat`; it clears the pid file safely.

Safety notes:

- Commands are duration-limited to 30 seconds.
- `toy_stop` has higher queue priority and can interrupt a running sequence.
- If the bridge is not open, commands remain queued until the bridge starts.
- The queue was last checked with no `pending` or `running` toy records.

## Design Boundaries

- `xiaoke-actions` is only an action outlet. It does not decide whether Claude should send a note.
- Category and intent are metadata, not routing or decision logic in this first version.
- Active messages should keep using this unified outlet instead of bypassing Claude and posting to ntfy directly.
- Monitoring, wake orchestration, and memory logic should not be added to this service.
