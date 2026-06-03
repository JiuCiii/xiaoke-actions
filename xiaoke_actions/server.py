from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from .action_queue import ActionQueueError, SupabaseActionQueue
from .config import load_config
from .guardrails import ActionGuardrails
from .ntfy import NtfyError, send_ntfy
from .toy import ToyController, ToyError


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("xiaoke-actions")

config = load_config()
guardrails = ActionGuardrails(config)
toy_controller = ToyController(
    main_address=config.toy_main_address,
    vibrator_address=config.toy_vibrator_address,
)
action_queue = SupabaseActionQueue(config)

mcp = FastMCP(
    "xiaoke-actions",
    instructions=(
        "Action tools for Xiaoke. Use send_note when Xiaoke intentionally wants "
        "to send a short note to Xiaomao's phone. The server only delivers actions "
        "with safety guardrails; it does not decide Xiaoke's intent."
    ),
    stateless_http=True,
    json_response=True,
    host=config.host,
    port=config.port,
    streamable_http_path=config.mcp_path,
)


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def root_health(_request) -> JSONResponse:
    return _health_response()


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_request) -> JSONResponse:
    return _health_response()


@mcp.tool()
def send_note(
    message: str,
    title: str | None = None,
    urgency: str | None = "normal",
    category: str | None = "presence",
    intent: str | None = None,
) -> dict:
    """Send a short note to Xiaomao's phone through ntfy.

    Args:
        message: The note body. Keep it concise.
        title: Optional notification title. Defaults to Claude.
        urgency: One of low, normal, high, urgent. Defaults to normal.
        category: One of presence, monitor, task, memory, system. Defaults to presence.
        intent: Optional short freeform purpose tag, such as affection or wake_error.
    """
    decision = guardrails.check(
        message=message,
        title=title,
        urgency=urgency,
        category=category,
        intent=intent,
    )
    audit = {
        "tool": "send_note",
        "allowed": decision.allowed,
        "reason": decision.reason,
        "category": decision.category,
        "intent": decision.intent,
        "urgency": decision.urgency,
        "title": decision.title,
        "message_chars": len(decision.message),
    }

    if not decision.allowed:
        logger.info("action_blocked %s", json.dumps(audit, ensure_ascii=False))
        return {
            "ok": False,
            "delivered": False,
            "reason": decision.reason,
            "category": decision.category,
            "intent": decision.intent,
            "urgency": decision.urgency,
        }

    try:
        response = send_ntfy(
            config=config,
            message=decision.message,
            title=decision.title,
            priority=decision.priority,
        )
    except NtfyError as exc:
        logger.exception("action_failed %s", json.dumps(audit, ensure_ascii=False))
        return {
            "ok": False,
            "delivered": False,
            "reason": "ntfy_error",
            "error": str(exc),
            "category": decision.category,
            "intent": decision.intent,
            "urgency": decision.urgency,
        }

    audit["ntfy_status"] = response["status"]
    logger.info("action_delivered %s", json.dumps(audit, ensure_ascii=False))
    return {
        "ok": True,
        "delivered": True,
        "reason": "sent",
        "ntfy_status": response["status"],
        "category": decision.category,
        "intent": decision.intent,
        "urgency": decision.urgency,
    }


@mcp.tool()
def toy_status() -> dict:
    """Return configured SVAKOM toy devices and safety limits."""
    status = toy_controller.status()
    status["queue"] = {
        "type": "supabase",
        "configured": action_queue.is_configured(),
        "table": config.action_queue_table,
    }
    status["armed"] = config.toy_armed
    return status


@mcp.tool()
def toy_diagnostics(limit: int = 5) -> dict:
    """Return toy bridge configuration and recent queue health without moving the toy."""
    status = toy_status()
    diagnostics = {
        "ok": True,
        "status": status,
        "bridge": None,
        "queue_counts": {},
        "recent": [],
        "warnings": [],
        "warning_details": {},
    }
    if not action_queue.is_configured():
        diagnostics["ok"] = False
        diagnostics["warnings"].append("action_queue_not_configured")
        return diagnostics

    try:
        bridge = action_queue.bridge_status()
        counts = action_queue.status_counts(domain="toy")
        recent = action_queue.recent(domain="toy", limit=limit)
    except ActionQueueError as exc:
        diagnostics["ok"] = False
        diagnostics["warnings"].append(str(exc))
        return diagnostics

    diagnostics["bridge"] = _bridge_status_summary(bridge)
    diagnostics["queue_counts"] = counts
    diagnostics["recent"] = [_toy_record_summary(row) for row in recent]
    bridge_fresh = diagnostics["bridge"] and diagnostics["bridge"].get("fresh")
    if not bridge:
        diagnostics["warnings"].append("toy_bridge_status_missing")
    elif not bridge_fresh:
        diagnostics["warnings"].append("toy_bridge_stale_or_offline")
    elif not (bridge.get("payload") or {}).get("local_armed"):
        diagnostics["warnings"].append("toy_bridge_disarmed")
    if counts.get("pending", 0) > 0:
        diagnostics["warnings"].append("toy_commands_pending")
    if counts.get("running", 0) > 0:
        diagnostics["warnings"].append("toy_commands_running")
    if not config.toy_armed:
        diagnostics["warnings"].append("remote_mcp_disarmed")
        diagnostics["warning_details"]["remote_mcp_disarmed"] = (
            "The hosted MCP server is intentionally not armed for direct local execution. "
            "Toy commands are queued remotely and executed only by the local bridge; "
            "use bridge.local_armed to determine whether queued non-stop commands can run."
        )
    diagnostics["ok"] = not any(
        warning in {
            "toy_bridge_status_missing",
            "toy_bridge_stale_or_offline",
            "toy_commands_pending",
            "toy_commands_running",
        }
        for warning in diagnostics["warnings"]
    )
    return diagnostics


@mcp.tool()
def toy_safety_status() -> dict:
    """Return a concise read-only answer about whether queued toy actions can run now."""
    diagnostics = toy_diagnostics(limit=1)
    bridge = diagnostics.get("bridge") or {}
    queue_counts = diagnostics.get("queue_counts") or {}
    bridge_ready = bool(
        bridge.get("status") == "online"
        and bridge.get("fresh")
        and bridge.get("local_armed")
    )
    queue_idle = queue_counts.get("pending", 0) == 0 and queue_counts.get("running", 0) == 0
    queue_configured = bool((diagnostics.get("status") or {}).get("queue", {}).get("configured"))
    can_execute_non_stop = bool(queue_configured and bridge_ready and queue_idle)
    return {
        "ok": can_execute_non_stop,
        "can_execute_non_stop": can_execute_non_stop,
        "can_queue_stop": queue_configured,
        "bridge_ready": bridge_ready,
        "queue_idle": queue_idle,
        "queue_counts": queue_counts,
        "bridge": bridge,
        "warnings": diagnostics.get("warnings") or [],
        "warning_details": diagnostics.get("warning_details") or {},
        "next_step": _toy_safety_next_step(
            queue_configured=queue_configured,
            bridge=bridge,
            queue_idle=queue_idle,
        ),
    }


@mcp.tool()
def toy_command(
    action: str,
    seconds: float | None = None,
    mode: int | None = None,
    level: int | None = None,
    preset: str | None = None,
    device: str | None = None,
    intent: str | None = None,
) -> dict:
    """Queue a semantic toy command for the local bridge.

    action is main, vibe, or stop. main controls the SX176A-01 circle route
    frequency 1-10 in the current manual function group. vibe controls the
    separate SX176A-02 vibrator level 1-6. stop is highest priority.
    """
    try:
        action_name, payload, priority = _toy_payload(
            action=action,
            seconds=seconds,
            mode=mode,
            level=level,
            preset=preset,
            device=device,
            intent=intent,
        )
        record = action_queue.enqueue(
            domain="toy",
            action=action_name,
            payload=payload,
            priority=priority,
            source="xiaoke-actions",
        )
    except (ToyError, ActionQueueError) as exc:
        return {"ok": False, "action": action, "reason": str(exc)}
    logger.info("toy_queued %s", json.dumps(record.__dict__, ensure_ascii=False))
    return {"ok": True, "queued": True, "id": record.id, "action": record.action, "payload": record.payload}


@mcp.tool()
def toy_main(mode: int, seconds: float, intent: str | None = None) -> dict:
    """Queue the main SX176A-01 circle-button route for a limited duration."""
    return toy_command(action="main", mode=mode, seconds=seconds, intent=intent)


@mcp.tool()
def toy_vibe(level: int, seconds: float, intent: str | None = None) -> dict:
    """Queue the separate SX176A-02 vibrator for a limited duration."""
    return toy_command(action="vibe", level=level, seconds=seconds, intent=intent)


@mcp.tool()
def toy_stop(device: str = "all", intent: str | None = None) -> dict:
    """Queue an immediate stop for the main toy, vibrator, or both."""
    return toy_command(action="stop", device=device, intent=intent)


@mcp.tool()
def toy_sequence(steps: list[dict], intent: str | None = None) -> dict:
    """Queue a sequence of toy steps for the local bridge to execute in order."""
    try:
        cleaned_steps = [_clean_sequence_step(step) for step in steps]
        record = action_queue.enqueue(
            domain="toy",
            action="sequence",
            payload={"steps": cleaned_steps, "intent": intent},
            priority=0,
            source="xiaoke-actions",
        )
    except (ToyError, ActionQueueError) as exc:
        return {"ok": False, "action": "sequence", "reason": str(exc)}
    logger.info("toy_sequence_queued %s", json.dumps(record.__dict__, ensure_ascii=False))
    return {"ok": True, "queued": True, "id": record.id, "action": "sequence", "payload": record.payload}


def _toy_payload(
    *,
    action: str,
    seconds: float | None,
    mode: int | None,
    level: int | None,
    preset: str | None,
    device: str | None,
    intent: str | None,
) -> tuple[str, dict, int]:
    action_name = (action or "").strip().lower()
    cleaned_device = (device or "all").strip().lower()
    if action_name == "stop":
        if cleaned_device not in {"main", "vibrator", "all"}:
            raise ToyError("unknown_device")
        return "stop", {"device": cleaned_device, "intent": intent}, 1000

    if seconds is None:
        raise ToyError("seconds_required")
    cleaned_seconds = _clean_seconds(seconds)

    if action_name == "main":
        cleaned_mode = mode if mode is not None else _preset_to_main_mode(preset)
        if cleaned_mode is None or not 1 <= cleaned_mode <= 10:
            raise ToyError("main_mode_must_be_1_10")
        return "main", {"mode": cleaned_mode, "seconds": cleaned_seconds, "intent": intent}, 0

    if action_name == "vibe":
        cleaned_level = level if level is not None else _preset_to_vibe_level(preset)
        if cleaned_level is None or not 1 <= cleaned_level <= 6:
            raise ToyError("vibe_level_must_be_1_6")
        return "vibe", {"level": cleaned_level, "seconds": cleaned_seconds, "intent": intent}, 0

    raise ToyError("unknown_toy_action")


def _clean_sequence_step(step: dict) -> dict:
    if not isinstance(step, dict):
        raise ToyError("sequence_step_must_be_object")
    action_name, payload, _priority = _toy_payload(
        action=str(step.get("action") or ""),
        seconds=step.get("seconds"),
        mode=step.get("mode"),
        level=step.get("level"),
        preset=step.get("preset"),
        device=step.get("device"),
        intent=step.get("intent"),
    )
    if action_name == "stop":
        raise ToyError("sequence_steps_cannot_be_stop")
    return {"action": action_name, **payload}


def _toy_record_summary(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "action": row.get("action"),
        "status": row.get("status"),
        "payload": row.get("payload") or {},
        "created_at": row.get("created_at"),
        "claimed_at": row.get("claimed_at"),
        "finished_at": row.get("finished_at"),
        "error": row.get("error"),
        "result": row.get("result"),
    }


def _bridge_status_summary(row: dict | None) -> dict | None:
    if not row:
        return None
    payload = row.get("payload") or {}
    updated_at = payload.get("updated_at") or row.get("finished_at")
    age_seconds = _age_seconds(updated_at)
    return {
        "status": row.get("status"),
        "local_armed": payload.get("local_armed"),
        "pid": payload.get("pid"),
        "updated_at": updated_at,
        "age_seconds": age_seconds,
        "fresh": row.get("status") == "online" and age_seconds is not None and age_seconds <= 60,
        "devices": payload.get("devices") or {},
    }


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _toy_safety_next_step(*, queue_configured: bool, bridge: dict, queue_idle: bool) -> str:
    if not queue_configured:
        return "configure_supabase_queue"
    if not bridge:
        return "run_arm_and_start_toy_bridge_bat"
    if bridge.get("status") != "online" or not bridge.get("fresh"):
        return "run_arm_and_start_toy_bridge_bat"
    if not bridge.get("local_armed"):
        return "run_arm_and_start_toy_bridge_bat"
    if not queue_idle:
        return "wait_for_queue_or_call_toy_stop_if_needed"
    return "ready_for_one_approved_toy_action"


def _clean_seconds(seconds: float) -> float:
    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ToyError("seconds_must_be_number") from exc
    if value <= 0:
        raise ToyError("seconds_must_be_positive")
    return min(value, 30.0)


def _preset_to_main_mode(preset: str | None) -> int | None:
    if not preset:
        return None
    return {
        "soft": 1,
        "gentle": 1,
        "light": 2,
        "steady": 3,
        "medium": 5,
        "strong": 8,
        "max": 10,
    }.get(preset.strip().lower())


def _preset_to_vibe_level(preset: str | None) -> int | None:
    if not preset:
        return None
    return {
        "soft": 1,
        "gentle": 1,
        "light": 2,
        "medium": 3,
        "strong": 5,
        "max": 6,
    }.get(preset.strip().lower())


def _health_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "xiaoke-actions",
            "mcp_path": config.mcp_path,
            "tools": {
                "send_note": True,
                "toy": True,
            },
        }
    )


def main() -> None:
    logger.info(
        "starting xiaoke-actions host=%s port=%s path=%s",
        config.host,
        config.port,
        config.mcp_path,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
