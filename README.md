# golem-telegram

Telegram channel for [Golem](https://github.com/terracotta4u/golem).

## Install

```bash
golem extension add https://github.com/terracotta4u/golem-telegram
```

## Setup

Create a bot with [@BotFather](https://t.me/BotFather). Export its token in the shell that runs Golem, then start the server:

```bash
export TELEGRAM_BOT_TOKEN=...
golem serve
```

Restart `golem serve` if it is already running so the extension inherits the token.

## Usage

Message the bot in a private chat. In a group, mention it or reply to one of its messages.
