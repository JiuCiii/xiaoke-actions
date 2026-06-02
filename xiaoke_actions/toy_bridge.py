from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Any

from .action_queue import QueueRecord, SupabaseActionQueue
from .config import load_config
from .toy import ToyController, ToyError


logger = logging.getLogger("xiaoke-toy-bridge")


class ToyBridge:
    def __init__(self, poll_seconds: float = 1.0, pid_file: str | None = None):
        self.queue = SupabaseActionQueue(load_config())
        self.controller = ToyController()
        self.poll_seconds = poll_seconds
        self.pid_file = pid_file

    async def run_forever(self) -> None:
        if not self.queue.is_configured():
            raise ToyError("supabase_not_configured")
        self._write_pid()
        logger.info("toy bridge started")
        try:
            while True:
                try:
                    record = self.queue.claim_next(domain="toy")
                    if record is not None:
                        await self._handle_record(record)
                except Exception:
                    logger.exception("toy bridge loop error")
                await asyncio.sleep(self.poll_seconds)
        finally:
            self._remove_pid()

    async def _handle_record(self, record: QueueRecord) -> None:
        logger.info("handling %s", json.dumps(record.__dict__, ensure_ascii=False))
        try:
            result = await self._execute(record)
        except Exception as exc:
            logger.exception("record failed id=%s", record.id)
            self.queue.mark_error(record.id, str(exc))
        else:
            self.queue.mark_done(record.id, result)

    async def _execute(self, record: QueueRecord) -> dict[str, Any]:
        if record.action == "stop":
            return await self._execute_stop(record.payload)
        if record.action == "main":
            return await self._execute_main(record.payload)
        if record.action == "vibe":
            return await self._execute_vibe(record.payload)
        if record.action == "sequence":
            return await self._execute_sequence(record.payload)
        raise ToyError("unknown_toy_action")

    async def _execute_sequence(self, payload: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for step in payload.get("steps") or []:
            stop_result = await self._consume_pending_stop()
            if stop_result is not None:
                return {"interrupted": True, "stop": stop_result, "results": results}
            action = step.get("action")
            if action == "main":
                results.append(await self._execute_main(step))
            elif action == "vibe":
                results.append(await self._execute_vibe(step))
            else:
                raise ToyError("unknown_sequence_step")
        return {"ok": True, "results": results}

    async def _execute_main(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = int(payload["mode"])
        seconds = float(payload["seconds"])
        start = await self.controller.start_main(mode)
        interrupted = await self._sleep_or_stop(seconds)
        if interrupted is not None:
            return {"started": start.__dict__, "interrupted": True, "stop": interrupted}
        stop = await self.controller.stop_device("main")
        return {"started": start.__dict__, "stopped": stop.__dict__}

    async def _execute_vibe(self, payload: dict[str, Any]) -> dict[str, Any]:
        level = int(payload["level"])
        seconds = float(payload["seconds"])
        start = await self.controller.start_vibe(level)
        interrupted = await self._sleep_or_stop(seconds)
        if interrupted is not None:
            return {"started": start.__dict__, "interrupted": True, "stop": interrupted}
        stop = await self.controller.stop_device("vibrator")
        return {"started": start.__dict__, "stopped": stop.__dict__}

    async def _sleep_or_stop(self, seconds: float) -> dict[str, Any] | None:
        deadline = asyncio.get_running_loop().time() + seconds
        while True:
            stop_result = await self._consume_pending_stop()
            if stop_result is not None:
                return stop_result
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.25, remaining))

    async def _consume_pending_stop(self) -> dict[str, Any] | None:
        record = self.queue.pending_stop()
        if record is None:
            return None
        self.queue.mark_running(record.id)
        try:
            result = await self._execute_stop(record.payload)
        except Exception as exc:
            self.queue.mark_error(record.id, str(exc))
            raise
        self.queue.mark_done(record.id, result)
        return result

    async def _execute_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = str(payload.get("device") or "all")
        results = await self.controller.stop(device=device)
        return {"ok": all(result.ok for result in results), "results": [result.__dict__ for result in results]}

    def _write_pid(self) -> None:
        if not self.pid_file:
            return
        os.makedirs(os.path.dirname(self.pid_file) or ".", exist_ok=True)
        with open(self.pid_file, "w", encoding="utf-8") as pid_file:
            pid_file.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        if not self.pid_file:
            return
        try:
            os.remove(self.pid_file)
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local SVAKOM toy bridge.")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--pid-file", default=".logs/toy_bridge.pid")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(ToyBridge(poll_seconds=args.poll_seconds, pid_file=args.pid_file).run_forever())


if __name__ == "__main__":
    main()
