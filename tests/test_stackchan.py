from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from xiaoke_actions import server
from xiaoke_actions.action_queue import QueueRecord
from xiaoke_actions.stackchan import (
    StackchanError,
    emote_command,
    move_head_command,
    speak_command,
    wiggle_command,
)


class FakeRequest:
    def __init__(self, *, token: str = "device-secret", body: dict | None = None):
        self.headers = {
            "authorization": f"Bearer {token}",
            "x-stackchan-device": "stackchan-test",
        }
        self._body = body or {}

    async def json(self):
        return self._body


class FakeStackchanQueue:
    def __init__(self):
        self.pending: list[QueueRecord] = []
        self.finished: list[tuple[str, bool]] = []
        self.counter = 0

    def is_configured(self):
        return True

    def enqueue_stackchan(self, *, action, payload, ttl_seconds, replace_pending, source="xiaoke-actions"):
        if replace_pending:
            self.pending = [record for record in self.pending if record.action != action]
        self.counter += 1
        record = QueueRecord(
            id=f"cmd-{self.counter}",
            domain="stackchan",
            action=action,
            payload=payload,
            status="pending",
            priority=0,
            created_at="2026-06-10T00:00:00+00:00",
            expires_at="2026-06-10T00:00:30+00:00" if ttl_seconds else None,
        )
        self.pending.append(record)
        return record

    def claim_stackchan(self, *, device_id):
        if not self.pending:
            return None
        record = self.pending.pop(0)
        return replace(record, status="running", claimed_at="2026-06-10T00:00:01+00:00")

    def finish_stackchan(self, *, record_id, ok, result, error):
        self.finished.append((record_id, ok))
        return {"id": record_id, "status": "done" if ok else "error"}


class StackchanCommandTests(unittest.TestCase):
    def test_speech_is_fifo_with_ttl(self) -> None:
        command = speak_command("  早上好，皮皮  ", ttl_seconds=30)
        self.assertEqual(command.payload["text"], "早上好，皮皮")
        self.assertEqual(command.ttl_seconds, 30)
        self.assertFalse(command.replace_pending)

    def test_state_commands_replace_pending(self) -> None:
        self.assertTrue(emote_command("happy").replace_pending)
        self.assertTrue(move_head_command(10, -20).replace_pending)

    def test_wiggle_is_short_lived_and_deduplicated(self) -> None:
        command = wiggle_command(ttl_seconds=10)
        self.assertEqual(command.ttl_seconds, 10)
        self.assertTrue(command.replace_pending)

    def test_invalid_expression_and_head_range_are_rejected(self) -> None:
        with self.assertRaises(StackchanError):
            emote_command("confused-but-purple")
        with self.assertRaises(StackchanError):
            move_head_command(90, 0)


class StackchanServerTests(unittest.TestCase):
    def test_tools_preserve_fifo_speech_and_replace_state(self) -> None:
        queue = FakeStackchanQueue()
        with patch.object(server, "action_queue", queue):
            first = server.stackchan_speak("第一句")
            second = server.stackchan_speak("第二句")
            server.stackchan_emote("happy")
            server.stackchan_emote("angry")

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual([record.action for record in queue.pending], ["speak", "speak", "emote"])
        self.assertEqual(queue.pending[-1].payload["expression"], "angry")

    def test_device_poll_and_result_complete_a_command(self) -> None:
        queue = FakeStackchanQueue()
        config = replace(server.config, stackchan_device_token="device-secret")
        with (
            patch.object(server, "action_queue", queue),
            patch.object(server, "config", config),
        ):
            server.stackchan_speak("测试台词")
            poll = asyncio.run(server.stackchan_poll(FakeRequest()))
            poll_body = json.loads(poll.body)
            command_id = poll_body["command"]["id"]
            result = asyncio.run(
                server.stackchan_result(
                    FakeRequest(body={"id": command_id, "ok": True, "result": {"spoken": True}})
                )
            )

        self.assertEqual(poll.status_code, 200)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(queue.finished, [(command_id, True)])

    def test_device_endpoint_rejects_wrong_token(self) -> None:
        config = replace(server.config, stackchan_device_token="device-secret")
        with patch.object(server, "config", config):
            response = asyncio.run(server.stackchan_poll(FakeRequest(token="wrong")))
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
