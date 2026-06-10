# xiaoke-actions

`xiaoke-actions` is a small MCP server for actions Xiaoke can take toward the outside world.

It currently exposes notification tools, queued SVAKOM toy controls, and a
lightweight Runtime Guard status tool.

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

Health endpoints are available at `/` and `/health`. They return a small public
process-liveness payload and do not expose secrets, private MCP paths, capability
status, or send actions.

## Runtime Guard

`system_status()` reports lightweight runtime status for the top-level
capabilities `send_note`, `toy_control`, and `toy_stop`.

- `enabled`: recent evidence confirms the capability is available.
- `degraded`: it remains partly usable but has a known limitation or recent failure.
- `disabled`: required configuration is missing or the capability is intentionally off.
- `unknown`: availability cannot currently be confirmed.

The status tool does not make synchronous network probes. It combines local
configuration facts with observations recorded by real action and diagnostics
calls. It never returns secrets, private MCP paths, or device addresses.

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

## Deployed Smoke Test

Set the private MCP URL locally, then run:

```powershell
.\scripts\smoke_mcp.cmd
```

Required local environment:

```text
XIAOKE_ACTIONS_MCP_URL=https://xiaoke-actions.onrender.com/mcp-xiaoke-your-private-path
XIAOKE_ACTIONS_REQUIRED_TOOLS=system_status,send_note,toy_safety_status
```

The script initializes the deployed MCP server and checks that the required
tools are visible. It redacts the private path in its output. The old public
`/mcp` path may return 404 by design when Render is configured with a private
`MCP_PATH`.

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

Claude connection:

- This repository only hosts the MCP server. Claude will not see these tools
  until its MCP client configuration points to the Render `/mcp` URL.
- After Claude is connected, it can call `toy_status` and `toy_diagnostics` to
  inspect the queue and configuration. It can call `toy_safety_status` for a
  concise yes/no answer about whether non-stop toy commands can execute now,
  then call `toy_main`, `toy_vibe`, `toy_stop`, or `toy_sequence` when
  appropriate.
- The local bridge still controls whether commands physically execute. If the
  bridge is closed or `TOY_ARMED` is not true, queued start commands will not
  move the toy.

Local usage:

1. Run `arm_and_start_toy_bridge.bat` from this folder to set
   `TOY_ARMED=true` and start one visible bridge window.
2. Run `disarm_and_stop_toy_bridge.bat` to set `TOY_ARMED=false` and stop the
   bridge.
3. `start_toy_bridge.bat` and `stop_toy_bridge.bat` are lower-level helpers.
4. If Windows shows a stale pid or the bridge is not running, run
   `disarm_and_stop_toy_bridge.bat`; it clears the pid file safely.
5. Set `TOY_ARMED=true` in the local `.env` only when you intentionally want
   the bridge to execute non-stop toy commands.
6. Override `TOY_MAIN_ADDRESS` or `TOY_VIBRATOR_ADDRESS` in `.env` if the
   paired devices are replaced or their BLE addresses change.

Safety notes:

- The bridge defaults to disarmed. When `TOY_ARMED` is not true, it still allows
  `toy_stop` but rejects `main`, `vibe`, and `sequence` commands.
- Commands are duration-limited to 30 seconds.
- `toy_stop` has higher queue priority and can interrupt a running sequence.
- If the bridge is not open, commands remain queued until the bridge starts.
- The queue was last checked with no `pending` or `running` toy records.

Claude toy flow:

1. Call `toy_diagnostics(limit=1)` first. Continue only when
   `bridge.status=online`, `bridge.fresh=true`, `bridge.local_armed=true`, and
   queue counts show `pending=0` and `running=0`.
   `toy_safety_status` can be used instead when Claude needs a shorter
   ready/not-ready answer.
2. Queue exactly one intended toy action. Prefer short, low-intensity tests
   first, such as `toy_vibe(level=1, seconds=2)` or
   `toy_main(mode=1, seconds=2)`.
3. For `toy_sequence`, wait at least 25-30 seconds before checking diagnostics.
   Sequence execution can make the bridge heartbeat look briefly older while
   BLE operations are in progress.
4. Call `toy_diagnostics(limit=2)` after waiting. Report whether the new record
   is `done`, whether each `started` and `stopped` result is `ok=true`, and
   whether the queue returned to `pending=0` and `running=0`.
5. If the only failure is a transient BLE discovery error such as
   `Device ... was not found`, retry the same low-intensity action once after a
   fresh healthy diagnostics check.
6. Treat `remote_mcp_disarmed` as an informational safety note for the hosted
   MCP server. Physical execution is controlled by the local bridge, so use
   `bridge.local_armed` as the execution gate for queued non-stop commands.

Copyable Claude prompt:

```text
Use the xiaoke-actions connector for this toy flow.

1. Call toy_diagnostics with limit=1. Do not move the toy yet.
2. Optionally call toy_safety_status for a concise readiness check.
3. Continue only if bridge.status is online, bridge.fresh is true,
   bridge.local_armed is true, and queue_counts pending/running are both 0.
4. Queue exactly this action: <describe the one action or sequence here>.
5. Wait 25-30 seconds before checking again.
6. Call toy_diagnostics with limit=2.
7. Report in Chinese: whether the new record is done, whether every started
   and stopped result is ok=true, whether pending/running returned to 0, and
   whether any warning matters. Treat remote_mcp_disarmed as informational;
   the execution gate is bridge.local_armed.
8. If the only failure is a transient BLE discovery error such as
   "Device ... was not found", do not escalate intensity. Say that one
   low-intensity retry is reasonable after a fresh healthy diagnostics check.
```

## Stack-chan

Stack-chan is another physical action outlet in this service. It shares the
Supabase Action Queue but uses `domain = stackchan` and its own command
semantics:

- `stackchan_speak(text)`: FIFO, 30-second TTL by default, never implicitly
  supersedes another sentence.
- `stackchan_emote(expression)`: latest pending expression wins.
- `stackchan_move_head(pitch, yaw)`: latest pending pose wins.
- `stackchan_wiggle()`: one-shot action with a 10-second TTL; duplicate pending
  wiggles collapse to the newest one.
- `stackchan_cancel(command_id)`: explicitly cancels an unclaimed command.
- `stackchan_status()`: returns heartbeat freshness, queue counts, and recent
  results.

Device endpoints:

```text
GET  /stackchan/poll
POST /stackchan/result
POST /stackchan/heartbeat
```

The device authenticates with `Authorization: Bearer <STACKCHAN_DEVICE_TOKEN>`
or `X-Stackchan-Token`. It never receives the Supabase service-role key.

Before deployment:

1. Apply `schema/stackchan_queue.sql` to the existing Supabase project.
2. Set a long random `STACKCHAN_DEVICE_TOKEN` in Render and on the device.
3. Deploy the service and run the MCP smoke test.
4. Run `scripts/stackchan_simulator.py` before connecting physical hardware.

The migration is intentionally separate from `schema/action_queue.sql` so it
can be reviewed and applied after the current wake stability test.

## Design Boundaries

- `xiaoke-actions` is only an action outlet. It does not decide whether Claude should send a note.
- Category and intent are metadata, not routing or decision logic in this first version.
- Active messages should keep using this unified outlet instead of bypassing Claude and posting to ntfy directly.
- Monitoring, wake orchestration, and memory logic should not be added to this service.
