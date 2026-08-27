from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from golem_telegram import handle
from golem_telegram.golem import Client
from golem_telegram.telegram import Bot, Chat, Message, User


class _State:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.turns: list[dict] = []


def _telegram_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            path = urlparse(self.path).path
            if path.endswith("/sendMessage"):
                state.sent.append(body)
                raw = json.dumps({"ok": True, "result": {"message_id": 1}}).encode()
            elif path.endswith("/sendChatAction"):
                raw = json.dumps({"ok": True, "result": True}).encode()
            else:
                raw = json.dumps({"ok": False, "description": path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def _golem_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            state.turns.append(body)
            raw = json.dumps({"id": "turn-1"}).encode()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            raw = json.dumps({"id": "turn-1", "status": "done", "text": "hello back"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def _serve(handler) -> tuple[str, ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return f"http://{host}:{port}", server, thread


@pytest.fixture
def servers(monkeypatch: pytest.MonkeyPatch) -> _State:
    state = _State()
    telegram_url, telegram_server, telegram_thread = _serve(_telegram_handler(state))
    golem_url, golem_server, golem_thread = _serve(_golem_handler(state))
    monkeypatch.setattr("golem_telegram.telegram.TELEGRAM_API", telegram_url)
    try:
        yield state, golem_url
    finally:
        telegram_server.shutdown()
        golem_server.shutdown()
        telegram_thread.join(timeout=2)
        golem_thread.join(timeout=2)


def test_handle_sends_golem_reply(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    bot.timeout = 2
    golem = Client(golem_url, "secret")
    msg = Message(
        message_id=1,
        chat=Chat(id=42, type="private"),
        from_user=User(id=10, username="alice"),
        text="hello",
    )
    stop = threading.Event()
    handle(bot, golem, msg, stop)
    assert state.turns == [{"channel": "telegram", "text": "hello"}]
    assert state.sent[-1]["chat_id"] == 42
    assert state.sent[-1]["text"] == "hello back"


def test_handle_start(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    golem = Client(golem_url, "secret")
    msg = Message(
        message_id=1,
        chat=Chat(id=42, type="private"),
        from_user=User(id=10, username="alice"),
        text="/start",
    )
    handle(bot, golem, msg, threading.Event())
    assert state.turns == []
    assert state.sent[-1]["text"] == "golem is listening."


def test_handle_strips_mention(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    golem = Client(golem_url, "secret")
    msg = Message(
        message_id=1,
        chat=Chat(id=42, type="group"),
        from_user=User(id=10, username="alice"),
        text="@golem hello",
    )
    handle(bot, golem, msg, threading.Event())
    assert state.turns == [{"channel": "telegram", "text": "hello"}]
