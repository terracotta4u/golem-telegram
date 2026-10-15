from __future__ import annotations

import os
import sys
import threading

from golem import Channel, Client, GolemError

from golem_telegram.telegram import Bot, Message, TelegramError, conversation_id


class Telegram(Channel):
    id = "telegram"

    def run(self, client: Client, stop: threading.Event) -> None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("set TELEGRAM_BOT_TOKEN")

        bot = Bot.connect(token)
        who = bot.username or f"id {bot.id}"
        print(f"golem-telegram: @{who} → {client.url}", file=sys.stderr, flush=True)

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
                    handle(bot, client, self.id, update.message, stop)
                except (GolemError, TelegramError) as exc:
                    print(f"error: {exc}", file=sys.stderr, flush=True)


def handle(
    bot: Bot,
    client: Client,
    channel: str,
    msg: Message | None,
    stop: threading.Event,
) -> None:
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
        reply = client.send(conversation_id(msg), channel, text)
        bot.send(msg.chat.id, msg.thread_id, reply)
    except GolemError as exc:
        bot.send(msg.chat.id, msg.thread_id, "error: " + str(exc))
        raise
    finally:
        typing_stop.set()
        thread.join(timeout=1)
