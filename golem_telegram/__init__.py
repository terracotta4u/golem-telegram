from __future__ import annotations

import os
import signal
import sys
import threading
from types import FrameType

from golem_telegram.golem import Client, GolemError
from golem_telegram.telegram import Bot, Message, TelegramError, conversation_id


def main() -> None:
    try:
        run()
    except (GolemError, TelegramError, ValueError) as exc:
        print(exc, file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


def run() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("set TELEGRAM_BOT_TOKEN")

    stop = threading.Event()

    def handle_signal(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    bot = Bot.connect(token)
    golem = Client.from_env()
    who = bot.username or f"id {bot.id}"
    print(f"golem-telegram: @{who} → {golem.url}", file=sys.stderr, flush=True)

    while not stop.is_set():
        try:
            golem.wait_ready()
            break
        except GolemError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            if stop.wait(2):
                return

    offset = 0
    while not stop.is_set():
        try:
            updates = bot.updates(offset)
        except TelegramError as exc:
            if stop.is_set():
                return
            print(f"error: {exc}", file=sys.stderr, flush=True)
            if stop.wait(2):
                return
            continue
        for update in updates:
            offset = update.update_id + 1
            try:
                handle(bot, golem, update.message, stop)
            except (GolemError, TelegramError) as exc:
                print(f"error: {exc}", file=sys.stderr, flush=True)


def handle(bot: Bot, golem: Client, msg: Message | None, stop: threading.Event) -> None:
    if stop.is_set() or not bot.addressed(msg) or msg is None:
        return

    text = msg.text.replace("@" + bot.username, "").strip() if bot.username else msg.text.strip()
    if not text:
        return
    if text == "/start":
        bot.send(msg.chat.id, msg.thread_id, "golem is listening.")
        return

    typing_stop = threading.Event()

    def keep_typing() -> None:
        bot.typing(msg.chat.id, msg.thread_id)
        while not typing_stop.wait(4):
            bot.typing(msg.chat.id, msg.thread_id)

    thread = threading.Thread(target=keep_typing, daemon=True)
    thread.start()
    try:
        reply = golem.send(conversation_id(msg), text)
        bot.send(msg.chat.id, msg.thread_id, reply)
    except GolemError as exc:
        bot.send(msg.chat.id, msg.thread_id, "error: " + str(exc))
        raise
    finally:
        typing_stop.set()
        thread.join(timeout=1)
