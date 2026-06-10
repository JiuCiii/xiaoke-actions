from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class StackchanError(ValueError):
    pass


EXPRESSIONS = {
    "neutral",
    "happy",
    "shy",
    "angry",
    "sad",
    "surprised",
    "thinking",
    "sleepy",
}


@dataclass(frozen=True)
class StackchanCommand:
    action: str
    payload: dict[str, Any]
    ttl_seconds: int | None
    replace_pending: bool


def speak_command(text: str, *, ttl_seconds: int) -> StackchanCommand:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        raise StackchanError("text_required")
    if len(cleaned) > 300:
        raise StackchanError("text_too_long")
    return StackchanCommand(
        action="speak",
        payload={"text": cleaned},
        ttl_seconds=max(1, min(int(ttl_seconds), 300)),
        replace_pending=False,
    )


def emote_command(expression: str) -> StackchanCommand:
    cleaned = (expression or "").strip().lower()
    if cleaned not in EXPRESSIONS:
        raise StackchanError("unknown_expression")
    return StackchanCommand(
        action="emote",
        payload={"expression": cleaned},
        ttl_seconds=None,
        replace_pending=True,
    )


def move_head_command(pitch: float, yaw: float) -> StackchanCommand:
    cleaned_pitch = _bounded_number(pitch, "pitch", -30.0, 30.0)
    cleaned_yaw = _bounded_number(yaw, "yaw", -45.0, 45.0)
    return StackchanCommand(
        action="move_head",
        payload={"pitch": cleaned_pitch, "yaw": cleaned_yaw},
        ttl_seconds=None,
        replace_pending=True,
    )


def wiggle_command(*, ttl_seconds: int) -> StackchanCommand:
    return StackchanCommand(
        action="wiggle",
        payload={},
        ttl_seconds=max(1, min(int(ttl_seconds), 60)),
        replace_pending=True,
    )


def _bounded_number(value: float, name: str, minimum: float, maximum: float) -> float:
    try:
        cleaned = float(value)
    except (TypeError, ValueError) as exc:
        raise StackchanError(f"{name}_must_be_number") from exc
    if not minimum <= cleaned <= maximum:
        raise StackchanError(f"{name}_out_of_range")
    return round(cleaned, 2)
