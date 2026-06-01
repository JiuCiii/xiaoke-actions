from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .guardrails import ActionGuardrails
from .ntfy import NtfyError, send_ntfy


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("xiaoke-actions")

config = load_config()
guardrails = ActionGuardrails(config)

mcp = FastMCP(
    "xiaoke-actions",
    instructions=(
        "Action tools for Xiaoke. Use send_note when Xiaoke intentionally wants "
        "to send a short note to Xiaomao's phone. The server only delivers actions "
        "with safety guardrails; it does not decide Xiaoke's intent."
    ),
    stateless_http=True,
    json_response=True,
    host=config.host,
    port=config.port,
    streamable_http_path=config.mcp_path,
)


@mcp.tool()
def send_note(message: str, title: str | None = None, urgency: str | None = "normal") -> dict:
    """Send a short note to Xiaomao's phone through ntfy.

    Args:
        message: The note body. Keep it concise.
        title: Optional notification title. Defaults to Xiaoke.
        urgency: One of low, normal, high, urgent. Defaults to normal.
    """
    decision = guardrails.check(message=message, title=title, urgency=urgency)
    audit = {
        "tool": "send_note",
        "allowed": decision.allowed,
        "reason": decision.reason,
        "urgency": decision.urgency,
        "title": decision.title,
        "message_chars": len(decision.message),
    }

    if not decision.allowed:
        logger.info("action_blocked %s", json.dumps(audit, ensure_ascii=False))
        return {
            "ok": False,
            "delivered": False,
            "reason": decision.reason,
        }

    try:
        response = send_ntfy(
            config=config,
            message=decision.message,
            title=decision.title,
            priority=decision.priority,
        )
    except NtfyError as exc:
        logger.exception("action_failed %s", json.dumps(audit, ensure_ascii=False))
        return {
            "ok": False,
            "delivered": False,
            "reason": "ntfy_error",
            "error": str(exc),
        }

    audit["ntfy_status"] = response["status"]
    logger.info("action_delivered %s", json.dumps(audit, ensure_ascii=False))
    return {
        "ok": True,
        "delivered": True,
        "reason": "sent",
        "ntfy_status": response["status"],
    }


def main() -> None:
    logger.info(
        "starting xiaoke-actions host=%s port=%s path=%s",
        config.host,
        config.port,
        config.mcp_path,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
