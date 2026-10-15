from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest
from golem import Client, GolemError

from golem_telegram import Telegram, handle
from golem_telegram.telegram import Bot, Chat, Message, User


class _State:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.turns: list[dict] = []
        self.me_calls = 0
        self.update_calls = 0
        self.release_poll = threading.Event()


def _telegram_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            path = urlparse(self.path).path
            if path.endswith("/getMe"):
                state.me_calls += 1
                raw = json.dumps(
                    {"ok": True, "result": {"id": 99, "is_bot": True, "username": "golem"}}
                ).encode()
            elif path.endswith("/getUpdates"):
                state.update_calls += 1
                if state.update_calls == 1:
                    result = [
                        {
                            "update_id": 1,
                            "message": {
                                "message_id": 1,
                                "from": {"id": 10, "is_bot": False, "username": "alice"},
                                "chat": {"id": 42, "type": "private"},
                                "text": "hello",
                            },
                        }
                    ]
                else:
                    state.release_poll.wait(2)
                    result = []
                raw = json.dumps({"ok": True, "result": result}).encode()
            elif path.endswith("/sendMessage"):
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
            turn_id = "turn-err" if body.get("text") == "explode" else "turn-1"
            raw = json.dumps({"id": turn_id}).encode()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path.endswith("/turn-err"):
                payload = 'event: error\ndata: {"error":"boom"}\n\n'
            else:
                payload = 'event: done\ndata: {"text":"hello back"}\n\n'
            raw = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
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
        state.release_poll.set()
        telegram_server.shutdown()
        golem_server.shutdown()
        telegram_thread.join(timeout=2)
        golem_thread.join(timeout=2)


def _message(text: str, chat_type: str = "private") -> Message:
    return Message(
        message_id=1,
        chat=Chat(id=42, type=chat_type),
        from_user=User(id=10, username="alice"),
        text=text,
    )


def test_handle_sends_golem_reply(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    bot.timeout = 2
    client = Client(golem_url, "secret")
    handle(bot, client, "telegram", _message("hello"), threading.Event())
    assert state.turns == [{"channel": "telegram", "text": "hello"}]
    assert state.sent[-1]["chat_id"] == 42
    assert state.sent[-1]["text"] == "hello back"


def test_handle_start(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    client = Client(golem_url, "secret")
    handle(bot, client, "telegram", _message("/start"), threading.Event())
    assert state.turns == []
    assert state.sent[-1]["text"] == "golem is listening."


def test_handle_strips_mention(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    client = Client(golem_url, "secret")
    handle(bot, client, "telegram", _message("@golem hello", "group"), threading.Event())
    assert state.turns == [{"channel": "telegram", "text": "hello"}]


def test_handle_reports_golem_error(servers: tuple[_State, str]) -> None:
    state, golem_url = servers
    bot = Bot(token="t", id=99, username="golem")
    client = Client(golem_url, "secret")
    with pytest.raises(GolemError, match="boom"):
        handle(bot, client, "telegram", _message("explode"), threading.Event())
    assert state.sent[-1]["text"] == "error: boom"


def test_run_polls_and_replies(servers: tuple[_State, str], monkeypatch: pytest.MonkeyPatch) -> None:
    state, golem_url = servers
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    stop = threading.Event()
    thread = threading.Thread(
        target=Telegram().run,
        args=(Client(golem_url, "secret"), stop),
        daemon=True,
    )
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not state.sent and thread.is_alive():
            time.sleep(0.05)
        assert state.turns == [{"channel": "telegram", "text": "hello"}]
        assert state.sent[-1]["text"] == "hello back"
        assert state.me_calls == 1
    finally:
        stop.set()
        state.release_poll.set()
        thread.join(timeout=2)


def test_run_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Telegram().run(Client("http://127.0.0.1:9"), threading.Event())
