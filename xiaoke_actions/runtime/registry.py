from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import Config
from .health import action_queue_configuration, send_note_configuration, unknown_status
from .status import CapabilityStatus, now_iso


class RuntimeGuard:
    """Tracks lightweight configuration facts and recent real-world observations."""

    CAPABILITIES = ("send_note", "toy_control", "toy_stop", "stackchan_speech", "stackchan_control")
    ACTION_OBSERVATION_TTL_SECONDS = 300
    EXECUTION_OBSERVATION_TTL_SECONDS = 90

    def __init__(self, config: Config):
        self.config = config
        self._observations: dict[str, CapabilityStatus] = {}

    def record_success(
        self,
        capability: str,
        *,
        reason_code: str,
        summary: str,
        source: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        checked_at = now_iso()
        previous = self._observations.get(capability)
        self._observations[capability] = CapabilityStatus(
            status="enabled",
            reason_code=reason_code,
            summary=summary,
            checked_at=checked_at,
            source=source,
            last_success_at=checked_at,
            last_failure_at=previous.last_failure_at if previous else None,
            details=details or {},
        )

    def record_failure(
        self,
        capability: str,
        *,
        reason_code: str,
        summary: str,
        source: str,
        next_step: str | None = None,
        details: dict[str, Any] | None = None,
        status: str = "degraded",
    ) -> None:
        checked_at = now_iso()
        previous = self._observations.get(capability)
        self._observations[capability] = CapabilityStatus(
            status=status,
            reason_code=reason_code,
            summary=summary,
            checked_at=checked_at,
            source=source,
            last_success_at=previous.last_success_at if previous else None,
            last_failure_at=checked_at,
            next_step=next_step,
            details=details or {},
        )

    def record_toy_diagnostics(self, diagnostics: dict[str, Any]) -> None:
        if not diagnostics.get("status", {}).get("queue", {}).get("configured"):
            return

        warnings = diagnostics.get("warnings") or []
        if any(str(warning).startswith("supabase_") for warning in warnings):
            self.record_failure(
                "action_queue",
                reason_code="action_queue_request_failed",
                summary="The most recent Action Queue check failed.",
                source="toy_diagnostics",
                next_step="check_supabase_queue",
            )
            return

        self.record_success(
            "action_queue",
            reason_code="action_queue_observed_available",
            summary="The Action Queue responded to the most recent diagnostics check.",
            source="toy_diagnostics",
        )

        bridge = diagnostics.get("bridge")
        if not bridge:
            self.record_failure(
                "toy_execution",
                reason_code="toy_bridge_status_missing",
                summary="No recent Toy Bridge status is available.",
                source="toy_diagnostics",
                next_step="run_arm_and_start_toy_bridge_bat",
                status="unknown",
            )
        elif bridge.get("status") != "online" or not bridge.get("fresh"):
            self.record_failure(
                "toy_execution",
                reason_code="toy_bridge_stale_or_offline",
                summary="The Toy Bridge is offline or its status is stale.",
                source="toy_diagnostics",
                next_step="run_arm_and_start_toy_bridge_bat",
                status="unknown",
            )
        elif not bridge.get("local_armed"):
            self.record_failure(
                "toy_execution",
                reason_code="toy_bridge_disarmed",
                summary="The Toy Bridge is online but intentionally disarmed.",
                source="toy_diagnostics",
                next_step="run_arm_and_start_toy_bridge_bat",
                status="disabled",
            )
        else:
            self.record_success(
                "toy_execution",
                reason_code="toy_bridge_ready",
                summary="The Toy Bridge was recently observed online, fresh, and armed.",
                source="toy_diagnostics",
                details={"observed_at": bridge.get("updated_at")},
            )

        self._record_stop_confirmation(diagnostics.get("recent") or [])

    def system_status(self) -> dict[str, Any]:
        checked_at = now_iso()
        status_builders = {
            "send_note": self._send_note_status,
            "toy_control": self._toy_control_status,
            "toy_stop": self._toy_stop_status,
            "stackchan_speech": self._stackchan_speech_status,
            "stackchan_control": self._stackchan_control_status,
        }
        capabilities = {
            capability: status_builders[capability]().to_dict()
            for capability in self.CAPABILITIES
        }
        return {
            "ok": True,
            "service": "xiaoke-actions",
            "checked_at": checked_at,
            "source": "runtime_guard_v1",
            "capabilities": capabilities,
        }

    def _send_note_status(self) -> CapabilityStatus:
        configuration = send_note_configuration(self.config)
        if configuration:
            return configuration
        return self._fresh_observation(
            "send_note",
            max_age_seconds=self.ACTION_OBSERVATION_TTL_SECONDS,
        ) or unknown_status(
            reason_code="send_note_not_observed",
            summary="send_note is configured, but no recent delivery result is available.",
            next_step="use_send_note_when_needed",
        )

    def _queue_status(self) -> CapabilityStatus:
        configuration = action_queue_configuration(self.config)
        if configuration:
            return configuration
        return self._fresh_observation(
            "action_queue",
            max_age_seconds=self.ACTION_OBSERVATION_TTL_SECONDS,
        ) or unknown_status(
            reason_code="action_queue_not_observed",
            summary="The Action Queue is configured, but no recent observation is available.",
            next_step="call_toy_diagnostics",
        )

    def _execution_status(self) -> CapabilityStatus:
        if action_queue_configuration(self.config):
            return unknown_status(
                reason_code="toy_execution_not_observable",
                summary="Toy execution cannot be observed until the Action Queue is configured.",
                next_step="configure_supabase_queue",
            )
        return self._fresh_observation(
            "toy_execution",
            max_age_seconds=self.EXECUTION_OBSERVATION_TTL_SECONDS,
        ) or unknown_status(
            reason_code="toy_execution_not_observed",
            summary="No recent Toy Bridge execution readiness observation is available.",
            next_step="call_toy_diagnostics",
        )

    def _toy_control_status(self) -> CapabilityStatus:
        queue = self._queue_status()
        execution = self._execution_status()
        details = {
            "queue": queue.to_dict(),
            "execution": execution.to_dict(),
            "can_queue": queue.status == "enabled",
            "can_execute": execution.status == "enabled",
        }

        if queue.status == "disabled":
            return self._aggregate(
                "disabled",
                "toy_control_queue_disabled",
                "toy_control is disabled because commands cannot be queued.",
                details,
                "configure_supabase_queue",
            )
        if queue.status == "enabled" and execution.status == "enabled":
            return self._aggregate(
                "enabled",
                "toy_control_ready",
                "toy_control can queue commands and the Toy Bridge was recently observed ready.",
                details,
            )
        if queue.status == "enabled" and execution.status == "disabled":
            return self._aggregate(
                "degraded",
                "toy_control_execution_disabled",
                "toy_control can queue commands, but the Toy Bridge is intentionally unavailable.",
                details,
                execution.next_step,
            )
        if queue.status == "degraded":
            return self._aggregate(
                "degraded",
                "toy_control_queue_degraded",
                "toy_control has a recent Action Queue failure.",
                details,
                queue.next_step,
            )
        return self._aggregate(
            "unknown",
            "toy_control_readiness_unknown",
            "toy_control readiness cannot currently be confirmed.",
            details,
            "call_toy_diagnostics",
        )

    def _toy_stop_status(self) -> CapabilityStatus:
        queue = self._queue_status()
        confirmation = self._observations.get("toy_stop_confirmation")
        details = {
            "can_submit": queue.status == "enabled",
            "queue": queue.to_dict(),
            "last_confirmation": confirmation.to_dict() if confirmation else None,
        }
        if queue.status == "disabled":
            return self._aggregate(
                "disabled",
                "toy_stop_queue_disabled",
                "toy_stop is disabled because a stop request cannot be queued.",
                details,
                "configure_supabase_queue",
            )
        if queue.status == "enabled":
            return self._aggregate(
                "enabled",
                "toy_stop_can_submit",
                "toy_stop can submit a stop request to the Action Queue.",
                details,
                "call_toy_diagnostics_to_confirm_execution" if not confirmation else None,
            )
        if queue.status == "degraded":
            return self._aggregate(
                "degraded",
                "toy_stop_queue_degraded",
                "toy_stop has a recent Action Queue failure.",
                details,
                queue.next_step,
            )
        return self._aggregate(
            "unknown",
            "toy_stop_submit_unknown",
            "Whether toy_stop can submit a stop request has not been observed since startup.",
            details,
            "call_toy_diagnostics",
        )

    def _stackchan_speech_status(self) -> CapabilityStatus:
        return self._stackchan_status("stackchan_speech", "speech")

    def _stackchan_control_status(self) -> CapabilityStatus:
        return self._stackchan_status("stackchan_control", "control")

    def _stackchan_status(self, capability: str, label: str) -> CapabilityStatus:
        if action_queue_configuration(self.config):
            return unknown_status(
                reason_code=f"{capability}_queue_not_configured",
                summary=f"Stack-chan {label} cannot queue commands until Supabase is configured.",
                next_step="configure_supabase_queue",
            )
        queue = self._fresh_observation(
            "stackchan_queue",
            max_age_seconds=self.ACTION_OBSERVATION_TTL_SECONDS,
        )
        device = self._fresh_observation(
            "stackchan_device",
            max_age_seconds=self.EXECUTION_OBSERVATION_TTL_SECONDS,
        )
        details = {
            "can_queue": bool(queue and queue.status == "enabled"),
            "device_endpoint_configured": bool(self.config.stackchan_device_token),
            "device": device.to_dict() if device else None,
        }
        if not self.config.stackchan_device_token:
            return self._aggregate(
                "disabled",
                f"{capability}_device_token_missing",
                f"Stack-chan {label} is disabled because the device endpoint token is not configured.",
                details,
                "configure_stackchan_device_token",
            )
        if queue and queue.status == "degraded":
            return self._aggregate(
                "degraded",
                f"{capability}_queue_degraded",
                f"Stack-chan {label} has a recent queue failure.",
                details,
                queue.next_step,
            )
        if queue and queue.status == "enabled" and device and device.status == "enabled":
            return self._aggregate(
                "enabled",
                f"{capability}_ready",
                f"Stack-chan {label} can queue commands and the device heartbeat is fresh.",
                details,
            )
        if queue and queue.status == "enabled":
            return self._aggregate(
                "degraded",
                f"{capability}_device_unobserved",
                f"Stack-chan {label} can queue commands, but no fresh device heartbeat is available.",
                details,
                "power_on_stackchan_and_check_status",
            )
        return self._aggregate(
            "unknown",
            f"{capability}_not_observed",
            f"Stack-chan {label} is configured, but queue readiness has not been observed.",
            details,
            "call_stackchan_status",
        )

    def _record_stop_confirmation(self, recent: list[dict[str, Any]]) -> None:
        stop_records = [record for record in recent if record.get("action") == "stop"]
        if not stop_records:
            return
        record = stop_records[0]
        record_status = record.get("status")
        details = {"record_id": record.get("id"), "record_status": record_status}
        if record_status == "done":
            self.record_success(
                "toy_stop_confirmation",
                reason_code="toy_stop_confirmed",
                summary="The most recently observed stop request was confirmed by the Toy Bridge.",
                source="toy_diagnostics",
                details=details,
            )
        elif record_status == "error":
            self.record_failure(
                "toy_stop_confirmation",
                reason_code="toy_stop_confirmation_failed",
                summary="The most recently observed stop request failed.",
                source="toy_diagnostics",
                next_step="inspect_toy_diagnostics",
                details=details,
            )

    def _fresh_observation(self, capability: str, *, max_age_seconds: int) -> CapabilityStatus | None:
        observation = self._observations.get(capability)
        if not observation:
            return None
        try:
            checked_at = datetime.fromisoformat(observation.checked_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age_seconds > max_age_seconds:
            return None
        return observation

    @staticmethod
    def _aggregate(
        status: str,
        reason_code: str,
        summary: str,
        details: dict[str, Any],
        next_step: str | None = None,
    ) -> CapabilityStatus:
        return CapabilityStatus(
            status=status,
            reason_code=reason_code,
            summary=summary,
            checked_at=now_iso(),
            source="aggregate",
            next_step=next_step,
            details=details,
        )
