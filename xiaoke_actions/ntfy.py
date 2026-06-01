from __future__ import annotations

import urllib.error
import urllib.request

from .config import Config


class NtfyError(RuntimeError):
    pass


def send_ntfy(config: Config, message: str, title: str, priority: str) -> dict[str, str | int]:
    data = message.encode("utf-8")
    headers = {
        "Title": title,
        "Priority": priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if config.ntfy_token:
        headers["Authorization"] = f"Bearer {config.ntfy_token}"

    request = urllib.request.Request(
        config.ntfy_url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise NtfyError(f"ntfy_http_error status={exc.code} body={body}") from exc
    except urllib.error.URLError as exc:
        raise NtfyError(f"ntfy_url_error reason={exc.reason}") from exc
