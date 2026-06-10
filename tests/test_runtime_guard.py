from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from xiaoke_actions.config import Config
from xiaoke_actions.runtime.guards import safely_record
from xiaoke_actions.runtime.registry import RuntimeGuard
from xiaoke_actions.runtime.status import CapabilityStatus


def make_config(
    *,
    ntfy_url: str = "https://ntfy.example/topic",
    supabase_url: str = "https://supabase.example",
    supabase_key: str = "private-service-key",
) -> Config:
    return Config(
        ntfy_url=ntfy_url,
        ntfy_token="private-ntfy-token",
        default_title="Claude",
        max_message_chars=500,
        rate_limit_per_hour=6,
        min_interval_seconds=30,
        dedupe_window_seconds=300,
        quiet_hours="",
        quiet_mode="suppress",
        timezone="Asia/Shanghai",
        host="0.0.0.0",
        port=8000,
        mcp_path="/private-mcp-path",
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        action_queue_table="action_queue",
        toy_armed=False,
        toy_main_address="private-main-address",
        toy_vibrator_address="private-vibrator-address",
    )


class RuntimeGuardTests(unittest.TestCase):
    def test_configured_but_unobserved_capabilities_are_unknown(self) -> None:
        status = RuntimeGuard(make_config()).system_status()["capabilities"]

        self.assertEqual(status["send_note"]["status"], "unknown")
        self.assertEqual(status["toy_control"]["status"], "unknown")
        self.assertEqual(status["toy_stop"]["status"], "unknown")
        self.assertEqual(status["stackchan_speech"]["status"], "disabled")
        self.assertEqual(status["stackchan_control"]["status"], "disabled")

    def test_stackchan_isolated_readiness(self) -> None:
        guard = RuntimeGuard(make_config())
        guard.config = replace(guard.config, stackchan_device_token="device-secret")
        guard.record_success(
            "stackchan_queue",
            reason_code="stackchan_enqueue_succeeded",
            summary="queued",
            source="test",
        )
        guard.record_success(
            "stackchan_device",
            reason_code="stackchan_heartbeat_fresh",
            summary="online",
            source="test",
        )

        status = guard.system_status()["capabilities"]
        self.assertEqual(status["stackchan_speech"]["status"], "enabled")
        self.assertEqual(status["stackchan_control"]["status"], "enabled")
        self.assertEqual(status["send_note"]["status"], "unknown")

    def test_missing_ntfy_only_disables_send_note(self) -> None:
        status = RuntimeGuard(make_config(ntfy_url="")).system_status()["capabilities"]

        self.assertEqual(status["send_note"]["status"], "disabled")
        self.assertEqual(status["send_note"]["reason_code"], "ntfy_not_configured")
        self.assertEqual(status["toy_control"]["status"], "unknown")

    def test_missing_queue_disables_toy_without_affecting_send_note(self) -> None:
        status = RuntimeGuard(make_config(supabase_url="", supabase_key="")).system_status()["capabilities"]

        self.assertEqual(status["send_note"]["status"], "unknown")
        self.assertEqual(status["toy_control"]["status"], "disabled")
        self.assertEqual(status["toy_stop"]["status"], "disabled")

    def test_ready_diagnostics_enable_toy_control(self) -> None:
        guard = RuntimeGuard(make_config())
        guard.record_toy_diagnostics(
            {
                "status": {"queue": {"configured": True}},
                "warnings": [],
                "bridge": {
                    "status": "online",
                    "fresh": True,
                    "local_armed": True,
                    "updated_at": "2026-06-05T00:00:00+00:00",
                },
                "recent": [],
            }
        )

        status = guard.system_status()["capabilities"]
        self.assertEqual(status["toy_control"]["status"], "enabled")
        self.assertTrue(status["toy_control"]["details"]["can_queue"])
        self.assertTrue(status["toy_control"]["details"]["can_execute"])
        self.assertEqual(status["toy_stop"]["status"], "enabled")

    def test_disarmed_bridge_degrades_control_but_stop_stays_available(self) -> None:
        guard = RuntimeGuard(make_config())
        guard.record_toy_diagnostics(
            {
                "status": {"queue": {"configured": True}},
                "warnings": ["toy_bridge_disarmed"],
                "bridge": {"status": "online", "fresh": True, "local_armed": False},
                "recent": [],
            }
        )

        status = guard.system_status()["capabilities"]
        self.assertEqual(status["toy_control"]["status"], "degraded")
        self.assertFalse(status["toy_control"]["details"]["can_execute"])
        self.assertEqual(status["toy_stop"]["status"], "enabled")

    def test_stop_confirmation_is_reported_separately(self) -> None:
        guard = RuntimeGuard(make_config())
        guard.record_toy_diagnostics(
            {
                "status": {"queue": {"configured": True}},
                "warnings": [],
                "bridge": {"status": "online", "fresh": True, "local_armed": True},
                "recent": [{"id": "stop-1", "action": "stop", "status": "done"}],
            }
        )

        stop = guard.system_status()["capabilities"]["toy_stop"]
        confirmation = stop["details"]["last_confirmation"]
        self.assertEqual(confirmation["reason_code"], "toy_stop_confirmed")
        self.assertEqual(confirmation["details"]["record_id"], "stop-1")

    def test_status_does_not_expose_secrets_or_private_paths(self) -> None:
        output = json.dumps(RuntimeGuard(make_config()).system_status())

        self.assertNotIn("private-service-key", output)
        self.assertNotIn("private-ntfy-token", output)
        self.assertNotIn("private-mcp-path", output)
        self.assertNotIn("private-main-address", output)
        self.assertNotIn("private-vibrator-address", output)

    def test_stale_success_returns_to_unknown(self) -> None:
        guard = RuntimeGuard(make_config())
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        guard._observations["send_note"] = CapabilityStatus(
            status="enabled",
            reason_code="ntfy_delivery_succeeded",
            summary="Old success.",
            checked_at=stale_time,
            source="send_note",
            last_success_at=stale_time,
        )

        send_note = guard.system_status()["capabilities"]["send_note"]
        self.assertEqual(send_note["status"], "unknown")

    def test_status_recording_failure_does_not_escape(self) -> None:
        def fail() -> None:
            raise RuntimeError("status bookkeeping failed")

        safely_record(fail)


if __name__ == "__main__":
    unittest.main()
