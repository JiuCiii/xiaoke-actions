from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from xiaoke_actions import server
from xiaoke_actions.action_queue import ActionQueueError
from xiaoke_actions.guardrails import ActionGuardrails
from xiaoke_actions.ntfy import NtfyError
from xiaoke_actions.runtime import RuntimeGuard


class FailingQueue:
    def enqueue(self, **_kwargs):
        raise ActionQueueError("supabase_url_error")


class ServerRuntimeIntegrationTests(unittest.TestCase):
    def test_send_note_failure_is_returned_and_observed(self) -> None:
        config = replace(
            server.config,
            ntfy_url="https://ntfy.example/topic",
            min_interval_seconds=0,
            quiet_hours="",
        )
        runtime_guard = RuntimeGuard(config)

        with (
            patch.object(server, "guardrails", ActionGuardrails(config)),
            patch.object(server, "runtime_guard", runtime_guard),
            patch.object(server, "send_ntfy", side_effect=NtfyError("temporary failure")),
        ):
            response = server.send_note("runtime guard integration test")

        self.assertFalse(response["ok"])
        status = runtime_guard.system_status()["capabilities"]
        self.assertEqual(status["send_note"]["status"], "degraded")
        self.assertNotEqual(status["toy_control"]["status"], "degraded")

    def test_toy_queue_failure_does_not_change_send_note(self) -> None:
        config = replace(
            server.config,
            supabase_url="https://supabase.example",
            supabase_key="private-key",
        )
        runtime_guard = RuntimeGuard(config)

        with (
            patch.object(server, "runtime_guard", runtime_guard),
            patch.object(server, "action_queue", FailingQueue()),
        ):
            response = server.toy_main(mode=1, seconds=1)

        self.assertFalse(response["ok"])
        status = runtime_guard.system_status()["capabilities"]
        self.assertEqual(status["toy_control"]["status"], "degraded")
        self.assertNotEqual(status["send_note"]["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
