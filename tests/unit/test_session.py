import pytest
from app.session.session import Session


class TestSession:
    def test_init(self):
        s = Session()
        assert s.messages == []
        assert s.assistant_partial == ""

    def test_add_user_turn(self):
        s = Session()
        s.add_user_turn("Hello")
        assert s.messages == [{"role": "user", "content": "Hello"}]
        s.add_user_turn("How are you?")
        assert len(s.messages) == 2
        assert s.messages[1] == {"role": "user", "content": "How are you?"}

    def test_append_assistant_partial(self):
        s = Session()
        s.append_assistant_partial("Hello")
        assert s.assistant_partial == "Hello"
        s.append_assistant_partial(", world!")
        assert s.assistant_partial == "Hello, world!"

    def test_finalize_assistant(self):
        s = Session()
        s.append_assistant_partial("Hello, world!")
        s.finalize_assistant()
        assert s.messages == [{"role": "assistant", "content": "Hello, world!"}]
        assert s.assistant_partial == ""

    def test_finalize_assistant_empty_partial(self):
        s = Session()
        s.finalize_assistant()
        assert s.messages == []
        assert s.assistant_partial == ""

    def test_discard_assistant_partial(self):
        s = Session()
        s.append_assistant_partial("Hello, world!")
        s.discard_assistant_partial()
        assert s.assistant_partial == ""
        assert s.messages == []

    def test_get_messages_no_partial(self):
        s = Session()
        s.add_user_turn("Hello")
        s.append_assistant_partial("Hi there!")
        s.finalize_assistant()
        msgs = s.get_messages()
        assert msgs == [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]

    def test_get_messages_with_partial(self):
        s = Session()
        s.add_user_turn("Hello")
        s.append_assistant_partial("Hi")
        msgs = s.get_messages()
        assert msgs == [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]

    def test_get_messages_empty(self):
        s = Session()
        assert s.get_messages() == []
