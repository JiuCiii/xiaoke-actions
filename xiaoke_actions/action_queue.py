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
STACKCHAN_STATUS_ID = "00000000-0000-4000-8000-000000000002"


@dataclass(frozen=True)
class QueueRecord:
    id: str
    domain: str
    action: str
    payload: dict[str, Any]
    status: str
    priority: int
    created_at: str | None = None
    claimed_at: str | None = None
    expires_at: str | None = None


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

    def enqueue_stackchan(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        ttl_seconds: int | None,
        replace_pending: bool,
        source: str = "xiaoke-actions",
    ) -> QueueRecord:
        rows = self._rpc(
            "stackchan_enqueue",
            {
                "p_action": action,
                "p_payload": payload,
                "p_ttl_seconds": ttl_seconds,
                "p_replace_pending": replace_pending,
                "p_source": source,
            },
        )
        if not rows:
            raise ActionQueueError("stackchan_enqueue_failed")
        return self._record(rows[0])

    def claim_stackchan(self, *, device_id: str) -> QueueRecord | None:
        rows = self._rpc("stackchan_claim_next", {"p_device_id": device_id})
        if not rows:
            return None
        return self._record(rows[0])

    def finish_stackchan(
        self,
        *,
        record_id: str,
        ok: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self._rpc(
            "stackchan_finish",
            {
                "p_id": record_id,
                "p_ok": ok,
                "p_result": result or {},
                "p_error": error,
            },
        )
        return rows[0] if rows else None

    def cancel_stackchan(self, *, record_id: str) -> dict[str, Any] | None:
        rows = self._rpc("stackchan_cancel", {"p_id": record_id})
        return rows[0] if rows else None

    def update_stackchan_status(self, *, device_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            **data,
            "device_id": device_id,
            "updated_at": _now_iso(),
        }
        body = {
            "id": STACKCHAN_STATUS_ID,
            "domain": "stackchan_bridge",
            "action": "heartbeat",
            "payload": payload,
            "status": "online",
            "priority": 0,
            "source": "stackchan-device",
            "finished_at": _now_iso(),
            "result": payload,
            "error": None,
        }
        rows = self._request(
            "POST",
            "",
            body=[body],
            query={"on_conflict": "id", "select": "*"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        return rows[0] if rows else None

    def stackchan_status(self) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            "",
            query={"id": f"eq.{STACKCHAN_STATUS_ID}", "limit": "1"},
        )
        return rows[0] if rows else None

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
        base_path: str | None = None,
    ) -> Any:
        if not self.is_configured():
            raise ActionQueueError("supabase_not_configured")

        query_string = f"?{urlencode(query)}" if query else ""
        resource = base_path or self.config.action_queue_table
        url = f"{self.config.supabase_url}/rest/v1/{resource}{path}{query_string}"
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

    def _rpc(self, function_name: str, body: dict[str, Any]) -> Any:
        return self._request(
            "POST",
            "",
            body=body,
            prefer="return=representation",
            base_path=f"rpc/{function_name}",
        )

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
            created_at=row.get("created_at"),
            claimed_at=row.get("claimed_at"),
            expires_at=row.get("expires_at"),
        )

    def status_counts(
        self,
        *,
        domain: str,
        statuses: tuple[str, ...] = ("pending", "running", "done", "error"),
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for status in statuses:
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
