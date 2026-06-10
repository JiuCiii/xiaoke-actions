from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_TOOLS = ("system_status", "send_note", "toy_safety_status")


def main() -> int:
    load_dotenv()
    url = os.getenv("XIAOKE_ACTIONS_MCP_URL", "").strip()
    required_tools = tuple(
        item.strip()
        for item in os.getenv("XIAOKE_ACTIONS_REQUIRED_TOOLS", ",".join(DEFAULT_REQUIRED_TOOLS)).split(",")
        if item.strip()
    )
    if not url:
        print_json(
            {
                "ok": False,
                "status": "not_configured",
                "env": "XIAOKE_ACTIONS_MCP_URL",
                "required_tools": required_tools,
            }
        )
        return 1

    try:
        init_response = post_json_rpc(
            url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "xiaoke-actions-smoke", "version": "1.0"},
                },
            },
        )
        tools_response = post_json_rpc(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print_json(
            {
                "ok": False,
                "status": "request_failed",
                "url": redact_url(url),
                "required_tools": required_tools,
                "error": str(exc),
            }
        )
        return 1

    tools = tool_names(tools_response)
    missing = [tool for tool in required_tools if tool not in tools]
    print_json(
        {
            "ok": not missing,
            "status": "tools_available" if not missing else "tools_missing",
            "url": redact_url(url),
            "required_tools": required_tools,
            "missing": missing,
            "tools": tools,
            "server": server_info(init_response),
        }
    )
    return 0 if not missing else 1


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def post_json_rpc(url: str, payload: dict[str, Any], timeout_seconds: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def tool_names(response: dict[str, Any]) -> list[str]:
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    tools = result.get("tools")
    if not isinstance(tools, list):
        return []
    return [tool["name"] for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]


def server_info(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    if not isinstance(result, dict):
        return {}
    server = result.get("serverInfo")
    return server if isinstance(server, dict) else {}


def redact_url(url: str) -> str:
    if "/mcp-" not in url:
        return url
    prefix, _secret = url.split("/mcp-", 1)
    return f"{prefix}/mcp-***"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
