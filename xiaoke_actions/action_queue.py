from __future__ import annotations

import json
import http.client
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Config


class ActionQueueError(RuntimeError):
    pass


TOY_BRIDGE_STATUS_ID = "00000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class QueueRecord:
    id: str
    domain: str
    action: str
    payload: dict[str, Any]
    status: str
    priority: int


class SupabaseActionQueue:
    def __init__(self, config: Config):
        self.config = config

    def is_configured(self) -> bool:
        return bool(self.config.supabase_url and self.config.supabase_key)

    def enqueue(
        self,
        *,
        domain: str,
        action: str,
        payload: dict[str, Any],
        priority: int = 0,
        source: str = "xiaoke-actions",
    ) -> QueueRecord:
        if not self.is_configured():
            raise ActionQueueError("supabase_not_configured")

        body = {
            "id": str(uuid.uuid4()),
            "domain": domain,
            "action": action,
            "payload": payload,
            "status": "pending",
            "priority": priority,
            "source": source,
        }
        rows = self._request("POST", "", body=[body], query={"select": "*"})
        if not rows:
            raise ActionQueueError("enqueue_failed")
        return self._record(rows[0])

    def claim_next(self, *, domain: str) -> QueueRecord | None:
        rows = self._request(
            "GET",
            "",
            query={
                "domain": f"eq.{domain}",
                "status": "eq.pending",
                "order": "priority.desc,created_at.asc",
                "limit": "1",
            },
        )
        if not rows:
            return None
        record = self._record(rows[0])
        self.mark_running(record.id)
        return record

    def pending_stop(self) -> QueueRecord | None:
        rows = self._request(
            "GET",
            "",
            query={
                "domain": "eq.toy",
                "action": "eq.stop",
                "status": "eq.pending",
                "order": "priority.desc,created_at.asc",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return self._record(rows[0])

    def mark_running(self, record_id: str) -> None:
        self._patch(record_id, {"status": "running", "claimed_at": _now_iso()})

    def mark_done(self, record_id: str, result: dict[str, Any]) -> None:
        self._patch(record_id, {"status": "done", "finished_at": _now_iso(), "result": result, "error": None})

    def mark_error(self, record_id: str, error: str) -> None:
        self._patch(record_id, {"status": "error", "finished_at": _now_iso(), "error": error})

    def _patch(self, record_id: str, body: dict[str, Any]) -> None:
        self._request("PATCH", "", body=body, query={"id": f"eq.{record_id}"})

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        query: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> Any:
        if not self.is_configured():
            raise ActionQueueError("supabase_not_configured")

        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{self.config.supabase_url}/rest/v1/{self.config.action_queue_table}{path}{query_string}"
        headers = {
            "apikey": self.config.supabase_key,
            "Authorization": f"Bearer {self.config.supabase_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if method == "POST":
            headers["Prefer"] = prefer or "return=representation"

        data = None if body is None else json.dumps(body).encode("utf-8")
        raw = self._urlopen_with_retries(url, data, headers, method)

        if not raw:
            return None
        return json.loads(raw)

    def _urlopen_with_retries(
        self,
        url: str,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(4):
            request = Request(url, data=data, headers=headers, method=method)
            try:
                with urlopen(request, timeout=20) as response:
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise ActionQueueError(f"supabase_http_{exc.code}: {detail}") from exc
            except (URLError, TimeoutError, OSError, http.client.RemoteDisconnected) as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
        raise ActionQueueError(f"supabase_url_error: {last_error}") from last_error

    @staticmethod
    def _record(row: dict[str, Any]) -> QueueRecord:
        return QueueRecord(
            id=row["id"],
            domain=row["domain"],
            action=row["action"],
            payload=row.get("payload") or {},
            status=row["status"],
            priority=int(row.get("priority") or 0),
        )

    def status_counts(self, *, domain: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for status in ("pending", "running", "done", "error"):
            rows = self._request(
                "GET",
                "",
                query={
                    "domain": f"eq.{domain}",
                    "status": f"eq.{status}",
                    "select": "id",
                },
            )
            counts[status] = len(rows or [])
        return counts

    def recent(self, *, domain: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._request(
            "GET",
            "",
            query={
                "domain": f"eq.{domain}",
                "order": "created_at.desc",
                "limit": str(max(1, min(limit, 20))),
            },
        )
        return rows or []

    def update_bridge_status(self, status: str, data: dict[str, Any]) -> dict[str, Any] | None:
        body = {
            "id": TOY_BRIDGE_STATUS_ID,
            "domain": "toy_bridge",
            "action": "heartbeat",
            "payload": data,
            "status": status,
            "priority": 0,
            "source": "local-toy-bridge",
            "finished_at": _now_iso(),
            "result": data,
            "error": None,
        }
        rows = self._request(
            "POST",
            "",
            body=[body],
            query={"on_conflict": "id", "select": "*"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            return None
        return rows[0]

    def bridge_status(self) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            "",
            query={
                "id": f"eq.{TOY_BRIDGE_STATUS_ID}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return rows[0]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
