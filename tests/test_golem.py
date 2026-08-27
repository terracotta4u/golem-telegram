from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from golem_telegram.golem import Client, GolemError


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _write_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        auth = self.headers.get("Authorization")
        if auth != "Bearer secret":
            self._write_json(401, {"error": "unauthorized"})
            return
        if self.path == "/v1/health":
            self._write_json(200, {"ok": True})
            return
        if self.path.startswith("/v1/turns/"):
            turn_id = self.path.rsplit("/", 1)[-1]
            if turn_id == "turn-1":
                polls = getattr(self.server, "polls", 0)
                self.server.polls = polls + 1  # type: ignore[attr-defined]
                if polls == 0:
                    self._write_json(200, {"id": "turn-1", "status": "pending"})
                    return
                self._write_json(200, {"id": "turn-1", "status": "done", "text": "hello back"})
                return
            if turn_id == "turn-err":
                self._write_json(200, {"id": "turn-err", "status": "error", "error": "boom"})
                return
            self._write_json(404, {"error": "turn not found"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        auth = self.headers.get("Authorization")
        if auth != "Bearer secret":
            self._write_json(401, {"error": "unauthorized"})
            return
        if self.path == "/v1/conversations/chat-1/turns":
            req = self._read_json()
            if req.get("channel") != "telegram" or req.get("text") != "hello":
                self._write_json(400, {"error": "bad body"})
                return
            self._write_json(202, {"id": "turn-1"})
            return
        if self.path == "/v1/conversations/chat-err/turns":
            self._write_json(202, {"id": "turn-err"})
            return
        self._write_json(404, {"error": "not found"})


@pytest.fixture
def golem_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.polls = 0  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_send_posts_turn_and_polls(golem_url: str) -> None:
    got = Client(golem_url, "secret").send("chat-1", "hello")
    assert got == "hello back"


def test_send_turn_error(golem_url: str) -> None:
    with pytest.raises(GolemError, match="boom"):
        Client(golem_url, "secret").send("chat-err", "hello")


def test_send_unauthorized(golem_url: str) -> None:
    with pytest.raises(GolemError, match="401"):
        Client(golem_url, "wrong").send("chat-1", "hello")


def test_wait_ready(golem_url: str) -> None:
    Client(golem_url, "secret").wait_ready(timeout=2)


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLEM_URL", "http://127.0.0.1:9999/")
    monkeypatch.setenv("GOLEM_TOKEN", "secret")
    client = Client.from_env()
    assert client.url == "http://127.0.0.1:9999"
    assert client.token == "secret"
