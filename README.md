# golem-telegram

A Golem channel extension. It long-polls Telegram, forwards addressed messages to a running Golem server, and sends the reply back.

Golem launches the `golem-telegram` console script from this package. It injects `GOLEM_URL` and `GOLEM_TOKEN`. The bot token comes from `TELEGRAM_BOT_TOKEN` in the process environment, or from `~/.golem/etc/conf.json` if you set it there.

## Message flow

1. Telegram delivers a message via `getUpdates`.
2. Private chats are always handled. Groups need an `@bot` mention or a reply to the bot.
3. The extension `POST`s `{channel: "telegram", text: "..."}` to `/v1/conversations/{chat-id}/turns`.
4. It polls `GET /v1/turns/{id}` until `done` or `error`.
5. The assistant text is sent back with `sendMessage`. Forum threads keep `chat-id:thread-id` as the conversation id.

## Setup

Create a bot with [@BotFather](https://t.me/BotFather) and export the token:

```sh
export TELEGRAM_BOT_TOKEN=...
```

Or set it in `~/.golem/etc/conf.json`:

```json
{
  "extensions": {
    "golem-telegram": {
      "env": {
        "TELEGRAM_BOT_TOKEN": "..."
      }
    }
  }
}
```

An empty conf value does not override a token already in the environment.

## Install

From this directory, after Golem is built:

```sh
golem extension add .
```

Replace an existing install with `--force`. Useful commands:

```sh
golem extension list
golem extension remove golem-telegram
```

Then start Golem:

```sh
golem serve
```

Disable without uninstalling by setting `"enabled": false` on that conf entry.

## Develop

```sh
uv sync --dev
uv run pytest
```
