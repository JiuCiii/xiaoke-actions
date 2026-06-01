from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Config


ALLOWED_URGENCY = {"low", "normal", "high", "urgent"}
ALLOWED_CATEGORY = {"presence", "monitor", "task", "memory", "system"}
NTFY_PRIORITY = {
    "low": "2",
    "normal": "3",
    "high": "4",
    "urgent": "5",
}


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str
    urgency: str
    priority: str
    title: str
    message: str
    category: str
    intent: str | None


class ActionGuardrails:
    def __init__(self, config: Config):
        self.config = config
        self._sent_at: deque[datetime] = deque()
        self._last_sent_at: datetime | None = None
        self._recent_fingerprints: dict[str, datetime] = {}

    def check(
        self,
        message: str,
        title: str | None,
        urgency: str | None,
        category: str | None,
        intent: str | None,
    ) -> GuardrailDecision:
        cleaned_message = " ".join((message or "").split())
        cleaned_title = " ".join((title or "").split()) or self.config.default_title
        cleaned_urgency = (urgency or "normal").strip().lower()
        if cleaned_urgency not in ALLOWED_URGENCY:
            cleaned_urgency = "normal"
        cleaned_category = (category or "presence").strip().lower()
        if cleaned_category not in ALLOWED_CATEGORY:
            cleaned_category = "presence"
        cleaned_intent = self._clean_intent(intent)

        if not self.config.ntfy_url:
            return self._deny(
                "ntfy_not_configured",
                cleaned_urgency,
                cleaned_title,
                cleaned_message,
                cleaned_category,
                cleaned_intent,
            )
        if not cleaned_message:
            return self._deny("empty_message", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)
        if len(cleaned_message) > self.config.max_message_chars:
            return self._deny("message_too_long", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)

        now = self._now()
        self._evict_old(now)

        if self._is_quiet_now(now):
            if self.config.quiet_mode == "suppress":
                return self._deny("quiet_hours", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)
            if self.config.quiet_mode == "downgrade":
                cleaned_urgency = "low"

        if (
            self._last_sent_at is not None
            and (now - self._last_sent_at).total_seconds() < self.config.min_interval_seconds
        ):
            return self._deny("min_interval", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)

        if len(self._sent_at) >= self.config.rate_limit_per_hour:
            return self._deny("hourly_rate_limit", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)

        fingerprint = self._fingerprint(cleaned_title, cleaned_message)
        if fingerprint in self._recent_fingerprints:
            return self._deny("duplicate_message", cleaned_urgency, cleaned_title, cleaned_message, cleaned_category, cleaned_intent)

        self._sent_at.append(now)
        self._last_sent_at = now
        self._recent_fingerprints[fingerprint] = now

        return GuardrailDecision(
            allowed=True,
            reason="allowed",
            urgency=cleaned_urgency,
            priority=NTFY_PRIORITY[cleaned_urgency],
            title=cleaned_title,
            message=cleaned_message,
            category=cleaned_category,
            intent=cleaned_intent,
        )

    def _deny(
        self,
        reason: str,
        urgency: str,
        title: str,
        message: str,
        category: str,
        intent: str | None,
    ) -> GuardrailDecision:
        return GuardrailDecision(
            allowed=False,
            reason=reason,
            urgency=urgency,
            priority=NTFY_PRIORITY.get(urgency, NTFY_PRIORITY["normal"]),
            title=title,
            message=message,
            category=category,
            intent=intent,
        )

    def _now(self) -> datetime:
        try:
            tz = ZoneInfo(self.config.timezone)
        except ZoneInfoNotFoundError:
            tz = timezone.utc
        return datetime.now(tz)

    def _evict_old(self, now: datetime) -> None:
        hour_ago = now.timestamp() - 3600
        while self._sent_at and self._sent_at[0].timestamp() < hour_ago:
            self._sent_at.popleft()

        dedupe_cutoff = now.timestamp() - self.config.dedupe_window_seconds
        expired = [
            fingerprint
            for fingerprint, sent_at in self._recent_fingerprints.items()
            if sent_at.timestamp() < dedupe_cutoff
        ]
        for fingerprint in expired:
            self._recent_fingerprints.pop(fingerprint, None)

    def _is_quiet_now(self, now: datetime) -> bool:
        if not self.config.quiet_hours:
            return False
        parts = self.config.quiet_hours.split("-", 1)
        if len(parts) != 2:
            return False
        start = self._parse_time(parts[0])
        end = self._parse_time(parts[1])
        if start is None or end is None:
            return False

        current = now.time()
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    @staticmethod
    def _parse_time(value: str) -> time | None:
        value = value.strip()
        try:
            hour, minute = value.split(":", 1)
            return time(hour=int(hour), minute=int(minute))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean_intent(value: str | None) -> str | None:
        cleaned = " ".join((value or "").split())
        if not cleaned:
            return None
        return cleaned[:48]

    @staticmethod
    def _fingerprint(title: str, message: str) -> str:
        raw = f"{title}\n{message}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
