from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class GolemError(Exception):
    pass


class Client:
    def __init__(self, url: str, token: str = "") -> None:
        self.url = url.rstrip("/")
        self.token = token

    @classmethod
    def from_env(cls) -> Client:
        url = os.environ.get("GOLEM_URL", "").strip() or "http://127.0.0.1:8743"
        token = os.environ.get("GOLEM_TOKEN", "").strip()
        return cls(url, token)

    def wait_ready(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                body = self._request("GET", "/v1/health")
                if body.get("ok"):
                    return
                last = GolemError("golem health not ok")
            except Exception as exc:
                last = exc
            time.sleep(0.4)
        if last is None:
            last = GolemError("golem not ready")
        raise GolemError(f"golem not ready: {last}") from last

    def send(self, conversation_id: str, text: str) -> str:
        accepted = self._request(
            "POST",
            f"/v1/conversations/{conversation_id}/turns",
            {"channel": "telegram", "text": text},
        )
        if accepted.get("error"):
            raise GolemError(accepted["error"])
        turn_id = accepted.get("id")
        if not turn_id:
            raise GolemError("missing turn id")
        return self._wait(turn_id)

    def _wait(self, turn_id: str) -> str:
        while True:
            turn = self._request("GET", f"/v1/turns/{turn_id}")
            status = turn.get("status")
            if status == "done":
                return turn.get("text") or ""
            if status == "error":
                raise GolemError(turn.get("error") or "turn failed")
            time.sleep(0.4)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = None
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise GolemError(f"unexpected status {exc.code}: {raw.decode(errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise GolemError(f"request failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GolemError(f"invalid json: {raw.decode(errors='replace')}") from exc
