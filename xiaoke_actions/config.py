from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    ntfy_url: str
    ntfy_token: str | None
    default_title: str
    max_message_chars: int
    rate_limit_per_hour: int
    min_interval_seconds: int
    dedupe_window_seconds: int
    quiet_hours: str
    quiet_mode: str
    timezone: str
    host: str
    port: int
    mcp_path: str


def load_config() -> Config:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    ntfy_url = os.getenv("NTFY_URL", "").strip()
    if not ntfy_url and topic:
        ntfy_url = f"https://ntfy.sh/{topic}"

    return Config(
        ntfy_url=ntfy_url,
        ntfy_token=os.getenv("NTFY_TOKEN") or None,
        default_title=os.getenv("DEFAULT_TITLE", "Xiaoke"),
        max_message_chars=_int_env("MAX_MESSAGE_CHARS", 500),
        rate_limit_per_hour=_int_env("RATE_LIMIT_PER_HOUR", 6),
        min_interval_seconds=_int_env("MIN_INTERVAL_SECONDS", 30),
        dedupe_window_seconds=_int_env("DEDUPE_WINDOW_SECONDS", 300),
        quiet_hours=os.getenv("QUIET_HOURS", "").strip(),
        quiet_mode=os.getenv("QUIET_MODE", "suppress").strip().lower(),
        timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=_int_env("PORT", 8000),
        mcp_path=os.getenv("MCP_PATH", "/mcp"),
    )
