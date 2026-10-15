# golem-telegram

A Golem channel extension. It long-polls Telegram, forwards addressed messages through [`golem-agent-sdk`](https://pypi.org/project/golem-agent-sdk/), and sends the reply back.

Golem launches this package with `python -m golem --name golem-telegram --channel telegram=golem_telegram:Telegram`. It injects `GOLEM_URL` and `GOLEM_TOKEN`. The SDK registers the process, heartbeats, and runs `Telegram`. The bot token comes from `TELEGRAM_BOT_TOKEN` in the process environment, or from `~/.golem/config.json` if you set it there.

## Message flow

1. Telegram delivers a message via `getUpdates`.
2. Private chats are always handled. Groups need an `@bot` mention or a reply to the bot.
3. `Client.send` posts `{channel: "telegram", text: "..."}` to `/v1/conversations/{chat-id}/turns` and reads the SSE stream until `done` or `error`.
4. The assistant text is sent back with `sendMessage`. Forum threads keep `chat-id:thread-id` as the conversation id.

## Setup

Create a bot with [@BotFather](https://t.me/BotFather) and export the token:

```sh
export TELEGRAM_BOT_TOKEN=...
```

Or set it in `~/.golem/config.json`:

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

An empty config value does not override a token already in the environment.

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

## Develop

```sh
uv sync --dev
uv run pytest
```

To run the channel against a local Golem server:

```sh
uv run python -m golem --name golem-telegram --channel telegram=golem_telegram:Telegram
```
