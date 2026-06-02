from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv() -> None:
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            cleaned_name = name.strip().lstrip("\ufeff")
            os.environ.setdefault(cleaned_name, value.strip().strip('"').strip("'"))


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    supabase_url: str
    supabase_key: str
    action_queue_table: str
    toy_armed: bool
    toy_main_address: str
    toy_vibrator_address: str


def load_config() -> Config:
    _load_dotenv()
    topic = os.getenv("NTFY_TOPIC", "").strip()
    ntfy_url = os.getenv("NTFY_URL", "").strip()
    if not ntfy_url and topic:
        ntfy_url = f"https://ntfy.sh/{topic}"

    return Config(
        ntfy_url=ntfy_url,
        ntfy_token=os.getenv("NTFY_TOKEN") or None,
        default_title=os.getenv("DEFAULT_TITLE", "Claude"),
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
        supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
        supabase_key=(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip(),
        action_queue_table=os.getenv("ACTION_QUEUE_TABLE", "action_queue").strip(),
        toy_armed=_bool_env("TOY_ARMED", False),
        toy_main_address=os.getenv("TOY_MAIN_ADDRESS", "33:74:7E:ED:80:D9").strip(),
        toy_vibrator_address=os.getenv("TOY_VIBRATOR_ADDRESS", "3D:B2:B4:ED:41:68").strip(),
    )
