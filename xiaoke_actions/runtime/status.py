from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_STATES = {"enabled", "degraded", "disabled", "unknown"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CapabilityStatus:
    status: str
    reason_code: str
    summary: str
    checked_at: str
    source: str
    last_success_at: str | None = None
    last_failure_at: str | None = None
    next_step: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATES:
            raise ValueError(f"invalid runtime status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "reason_code": self.reason_code,
            "summary": self.summary,
            "checked_at": self.checked_at,
            "source": self.source,
        }
        if self.last_success_at:
            result["last_success_at"] = self.last_success_at
        if self.last_failure_at:
            result["last_failure_at"] = self.last_failure_at
        if self.next_step:
            result["next_step"] = self.next_step
        if self.details:
            result["details"] = self.details
        return result
