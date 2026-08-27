from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE = 4096


class TelegramError(Exception):
    pass


@dataclass
class User:
    id: int
    is_bot: bool = False
    first_name: str = ""
    username: str = ""


@dataclass
class Chat:
    id: int
    type: str = "private"


@dataclass
class Message:
    message_id: int
    chat: Chat
    from_user: User | None = None
    text: str = ""
    thread_id: int = 0
    reply_to: Message | None = None


@dataclass
class Update:
    update_id: int
    message: Message | None = None


@dataclass
class Bot:
    token: str
    id: int = 0
    username: str = ""
    timeout: int = 60

    @classmethod
    def connect(cls, token: str) -> Bot:
        bot = cls(token=token)
        me = bot.get_me()
        bot.id = me.id
        bot.username = me.username
        return bot

    def get_me(self) -> User:
        return parse_user(self._call("getMe"))

    def updates(self, offset: int) -> list[Update]:
        raw = self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": 50,
                "allowed_updates": ["message"],
            },
            timeout=self.timeout,
        )
        if not isinstance(raw, list):
            return []
        return [parse_update(item) for item in raw]

    def send(self, chat_id: int, thread_id: int, text: str) -> None:
        if not text:
            text = "(no response)"
        for chunk in split_message(text):
            body: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if thread_id:
                body["message_thread_id"] = thread_id
            self._call("sendMessage", body)

    def typing(self, chat_id: int, thread_id: int) -> None:
        body: dict[str, Any] = {"chat_id": chat_id, "action": "typing"}
        if thread_id:
            body["message_thread_id"] = thread_id
        try:
            self._call("sendChatAction", body)
        except TelegramError:
            pass

    def addressed(self, msg: Message | None) -> bool:
        if msg is None or msg.from_user is None or msg.from_user.is_bot:
            return False
        if msg.chat.type == "private":
            return bool(msg.text)
        if (
            msg.reply_to is not None
            and msg.reply_to.from_user is not None
            and msg.reply_to.from_user.id == self.id
        ):
            return bool(msg.text)
        mention = "@" + self.username
        return bool(self.username) and contains_token(msg.text, mention)

    def _call(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> Any:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{TELEGRAM_API}/bot{self.token}/{method}",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise TelegramError(f"{method}: {raw.decode(errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"{method}: {exc.reason}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TelegramError(f"{method}: invalid json") from exc
        if not parsed.get("ok"):
            raise TelegramError(f"{method}: {parsed.get('description') or raw.decode(errors='replace')}")
        return parsed.get("result")


def parse_user(data: dict[str, Any]) -> User:
    return User(
        id=int(data.get("id") or 0),
        is_bot=bool(data.get("is_bot")),
        first_name=str(data.get("first_name") or ""),
        username=str(data.get("username") or ""),
    )


def parse_chat(data: dict[str, Any]) -> Chat:
    return Chat(id=int(data.get("id") or 0), type=str(data.get("type") or "private"))


def parse_message(data: dict[str, Any] | None) -> Message | None:
    if not data:
        return None
    from_raw = data.get("from")
    reply_raw = data.get("reply_to_message")
    return Message(
        message_id=int(data.get("message_id") or 0),
        chat=parse_chat(data.get("chat") or {}),
        from_user=parse_user(from_raw) if from_raw else None,
        text=str(data.get("text") or ""),
        thread_id=int(data.get("message_thread_id") or 0),
        reply_to=parse_message(reply_raw) if reply_raw else None,
    )


def parse_update(data: dict[str, Any]) -> Update:
    return Update(
        update_id=int(data.get("update_id") or 0),
        message=parse_message(data.get("message")),
    )


def conversation_id(msg: Message) -> str:
    ident = str(msg.chat.id)
    if msg.thread_id:
        return f"{ident}:{msg.thread_id}"
    return ident


def split_message(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE:
        return [text]
    return [text[i : i + MAX_MESSAGE] for i in range(0, len(text), MAX_MESSAGE)]


def contains_token(text: str, token: str) -> bool:
    if not token or not text:
        return False
    start = 0
    while True:
        i = text.find(token, start)
        if i < 0:
            return False
        left_ok = i == 0 or is_boundary(text[i - 1])
        right = i + len(token)
        right_ok = right == len(text) or is_boundary(text[right])
        if left_ok and right_ok:
            return True
        start = i + 1


def is_boundary(ch: str) -> bool:
    return ch in " \n\t,.!?"
