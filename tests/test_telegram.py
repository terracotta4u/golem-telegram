from golem_telegram.telegram import (
    Bot,
    Chat,
    Message,
    User,
    contains_token,
    conversation_id,
    parse_message,
    split_message,
)


def _msg(
    *,
    chat_id: int = 1,
    chat_type: str = "private",
    text: str = "hello",
    is_bot: bool = False,
    username: str = "alice",
    thread_id: int = 0,
    reply_to: Message | None = None,
) -> Message:
    return Message(
        message_id=1,
        chat=Chat(id=chat_id, type=chat_type),
        from_user=User(id=10, is_bot=is_bot, username=username),
        text=text,
        thread_id=thread_id,
        reply_to=reply_to,
    )


def test_addressed_private() -> None:
    bot = Bot(token="t", id=99, username="golem")
    assert bot.addressed(_msg())
    assert not bot.addressed(_msg(text=""))
    assert not bot.addressed(_msg(is_bot=True))


def test_addressed_group_mention() -> None:
    bot = Bot(token="t", id=99, username="golem")
    msg = _msg(chat_type="group", text="hey @golem do this")
    assert bot.addressed(msg)
    assert not bot.addressed(_msg(chat_type="group", text="hey @other"))
    assert not bot.addressed(_msg(chat_type="group", text="agolem"))


def test_addressed_group_reply_to_bot() -> None:
    bot = Bot(token="t", id=99, username="golem")
    reply = Message(
        message_id=2,
        chat=Chat(id=1, type="group"),
        from_user=User(id=99, is_bot=True, username="golem"),
        text="previous",
    )
    assert bot.addressed(_msg(chat_type="group", text="follow up", reply_to=reply))


def test_conversation_id() -> None:
    assert conversation_id(_msg(chat_id=-100)) == "-100"
    assert conversation_id(_msg(chat_id=-100, thread_id=7)) == "-100:7"


def test_split_message() -> None:
    assert split_message("hi") == ["hi"]
    long = "x" * 5000
    chunks = split_message(long)
    assert len(chunks) == 2
    assert "".join(chunks) == long
    assert all(len(c) <= 4096 for c in chunks)


def test_contains_token_boundaries() -> None:
    assert contains_token("hi @golem!", "@golem")
    assert not contains_token("hi@golem", "@golem")


def test_parse_message() -> None:
    msg = parse_message(
        {
            "message_id": 3,
            "from": {"id": 10, "is_bot": False, "username": "alice"},
            "chat": {"id": -42, "type": "group"},
            "text": "hello @golem",
            "message_thread_id": 9,
            "reply_to_message": {
                "message_id": 2,
                "from": {"id": 99, "is_bot": True, "username": "golem"},
                "chat": {"id": -42, "type": "group"},
                "text": "prev",
            },
        }
    )
    assert msg is not None
    assert msg.chat.id == -42
    assert msg.thread_id == 9
    assert msg.reply_to is not None
    assert msg.reply_to.from_user is not None
    assert msg.reply_to.from_user.id == 99
