from __future__ import annotations

from ..config import Config
from .status import CapabilityStatus, now_iso


def send_note_configuration(config: Config) -> CapabilityStatus | None:
    if config.ntfy_url:
        return None
    return CapabilityStatus(
        status="disabled",
        reason_code="ntfy_not_configured",
        summary="send_note is disabled because ntfy is not configured.",
        checked_at=now_iso(),
        source="configuration",
        next_step="configure_ntfy",
    )


def action_queue_configuration(config: Config) -> CapabilityStatus | None:
    if config.supabase_url and config.supabase_key:
        return None
    return CapabilityStatus(
        status="disabled",
        reason_code="action_queue_not_configured",
        summary="The Action Queue is disabled because Supabase is not configured.",
        checked_at=now_iso(),
        source="configuration",
        next_step="configure_supabase_queue",
    )


def unknown_status(*, reason_code: str, summary: str, next_step: str | None = None) -> CapabilityStatus:
    return CapabilityStatus(
        status="unknown",
        reason_code=reason_code,
        summary=summary,
        checked_at=now_iso(),
        source="runtime_memory",
        next_step=next_step,
    )
