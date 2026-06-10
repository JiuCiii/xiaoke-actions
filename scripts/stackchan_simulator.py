from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


def main() -> int:
    base_url = os.getenv("STACKCHAN_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("STACKCHAN_DEVICE_TOKEN", "").strip()
    device_id = os.getenv("STACKCHAN_DEVICE_ID", "stackchan-simulator").strip()
    if not token:
        print("STACKCHAN_DEVICE_TOKEN is required")
        return 1

    heartbeat = {
        "device_id": device_id,
        "firmware_version": "simulator-1",
        "rssi": -42,
        "free_heap": 123456,
        "current_action": None,
    }
    post_json(f"{base_url}/stackchan/heartbeat", token, heartbeat, device_id)
    print(f"simulator online: {device_id}")

    while True:
        response = request_json(f"{base_url}/stackchan/poll", token, device_id=device_id)
        command = response.get("command")
        if not command:
            time.sleep(2)
            continue

        print(json.dumps(command, ensure_ascii=False))
        action = command["action"]
        payload = command.get("payload") or {}
        if action == "speak":
            print(f"SPEAK: {payload.get('text')}")
        elif action == "emote":
            print(f"EMOTE: {payload.get('expression')}")
        elif action == "move_head":
            print(f"HEAD: pitch={payload.get('pitch')} yaw={payload.get('yaw')}")
        elif action == "wiggle":
            print("WIGGLE")

        post_json(
            f"{base_url}/stackchan/result",
            token,
            {"id": command["id"], "ok": True, "result": {"simulated": True}},
            device_id,
        )


def request_json(url: str, token: str, *, device_id: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Stackchan-Device": device_id,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, token: str, body: dict, device_id: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Stackchan-Device": device_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
