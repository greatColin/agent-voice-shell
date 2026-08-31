import pytest
from app.agent.pi_adapter import _ThinkFilter


def _drain(text: str) -> str:
    f = _ThinkFilter()
    out = f.feed(text) + f.flush()
    return out


class TestThinkFilter:
    def test_basic_think_block(self):
        out = _drain("think\nreasoning\nthink\nHello world.")
        assert out == "Hello world."

    def test_bracketed_think_block(self):
        out = _drain("<think>r1</think>Answer A")
        assert out == "Answer A"

    def test_inner_word_does_not_close_block(self):
        # Bare 'think' inside the reasoning text must NOT close the block.
        out = _drain("think\nI think about this carefully.\nthink\nThe answer is 42.")
        assert out == "The answer is 42."
        assert "think about" not in out

    def test_inner_word_v2(self):
        out = _drain("think\nstill thinking more\nthink\nReal answer.")
        assert out == "Real answer."

    def test_plain_text_passes_through(self):
        out = _drain("Just plain\ntext.\n")
        assert out == "Just plain\ntext.\n"

    def test_partial_open_tag_held(self):
        # 'thi' is a prefix of 'think' — must be held until the next chunk.
        f = _ThinkFilter()
        out1 = f.feed("thi")
        assert out1 == ""
        out2 = f.feed("nk\nreasoning\nthink\nAnswer B")
        assert out2.endswith("Answer B") or out2 + f.flush() == "Answer B"

    def test_split_think_across_chunks(self):
        f = _ThinkFilter()
        out1 = f.feed("thi")
        out2 = f.feed("nk>r</think>ok")
        out3 = f.flush()
        assert out1 + out2 + out3 == "ok"

    def test_overflow_emits_held_buffer(self):
        # A think block with no close tag and > 8000 chars falls back to emitting
        # the buffer so the rest of the answer is not silently dropped.
        text = "think" + "A" * 9000
        out = _drain(text)
        assert "A" in out

    def test_leading_whitespace_stripped(self):
        out = _drain("think\nr\nthink\n\n\n\nReal answer.")
        assert out == "Real answer."

    def test_empty_feed_is_noop(self):
        f = _ThinkFilter()
        assert f.feed("") == ""
        assert f.flush() == ""

    def test_open_in_middle_of_word_not_triggered(self):
        # OPEN requires ^ or \n before — the word 'something' should not open a think block.
        out = _drain("something interesting.")
        assert out == "something interesting."

    def test_bracketed_close_after_bare_open(self):
        out = _drain("think\nreasoning\n</think>after")
        assert out == "after"