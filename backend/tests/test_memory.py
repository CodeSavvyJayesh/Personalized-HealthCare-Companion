from memory import build_messages

SYSTEM = "you are a companion"


def test_history_is_replayed_so_the_bot_remembers():
    history = [
        {"sender": "user", "text": "my exams are stressing me"},
        {"sender": "bot", "text": "that sounds heavy"},
    ]
    messages = build_messages(SYSTEM, history, "it got worse today")

    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == "it got worse today"
    # The regression this guards: the old /chat sent only system + current.
    assert any("exams" in m["content"] for m in messages)


def test_summary_is_injected_as_context():
    messages = build_messages(SYSTEM, [], "hello", summary="- dealing with exams")
    assert messages[1]["role"] == "system"
    assert "exams" in messages[1]["content"]


def test_window_is_bounded():
    from config import settings

    history = [{"sender": "user", "text": f"msg {i}"} for i in range(500)]
    messages = build_messages(SYSTEM, history, "now")
    assert len(messages) <= settings.CHAT_WINDOW_TURNS * 2 + 2


def test_blank_messages_are_dropped():
    history = [{"sender": "user", "text": "   "}, {"sender": "bot", "text": "hi"}]
    messages = build_messages(SYSTEM, history, "hello")
    assert all(m["content"].strip() for m in messages)
