import asyncio
import os
import shlex
import sys
from typing import AsyncIterator

from app.agent.base import AgentClient
from app.events.events import Complete, TextChunk, VoiceEvent


def _resolve_pi_binary() -> str:
    """Locate the `pi` CLI. Honor $PI_BIN override, fall back to PATH lookup."""
    override = os.environ.get("PI_BIN")
    if override:
        return override
    found = (
        os.environ.get("PI_BINARY")
        or shutil_which("pi")
        or shutil_which("npx")
        or "/usr/local/bin/pi"
    )
    return found


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def _format_history(messages: list[dict]) -> str:
    """Render the conversation as a transcript for a single-turn pi prompt.

    pi is a coding agent with rich tools; for a voice shell we want a focused
    chat-style turn without tool access. We disable tools via --no-tools and
    append a system reminder so the model just answers the user's question.
    """
    lines = []
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            lines.append(f"[System]\n{content}")
        elif role == "assistant":
            lines.append(f"[Assistant]\n{content}")
        else:
            lines.append(f"[User]\n{content}")
    transcript = "\n\n".join(lines) if lines else ""
    if not transcript:
        return ""
    return (
        "You are a concise voice assistant. Answer the last user turn directly.\n"
        "Do not use tools. Do not narrate actions. Reply in the same language as the user.\n\n"
        f"{transcript}"
    )


class PiAdapter(AgentClient):
    """Streams responses by invoking the user's locally installed `pi` CLI.

    No credentials are stored in this repository. The provider and model are
    whatever the user has configured in their own `pi` setup (via `pi config`
    or environment variables like OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.).
    """

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._cancel_requested = False

    async def stream(self, messages: list[dict]) -> AsyncIterator[VoiceEvent]:
        self._cancel_requested = False

        prompt = _format_history(messages)
        if not prompt:
            yield Complete(final_text="(empty input)")
            return

        pi_bin = _resolve_pi_binary()
        cmd = [
            pi_bin,
            "-p",
            prompt,
            "--mode", "text",
            "--no-session",
            "--no-tools",
        ]

        extra_args = os.environ.get("PI_ARGS")
        if extra_args:
            cmd.extend(shlex.split(extra_args))

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            yield Complete(
                final_text=(
                    f"[agent] `pi` CLI not found ({pi_bin}). "
                    "Install it or set PI_BIN to your agent binary."
                )
            )
            return
        except Exception as e:
            yield Complete(final_text=f"[agent] failed to start pi: {e}")
            return

        buf: list[str] = []
        assert self._proc.stdout is not None
        try:
            while True:
                if self._cancel_requested:
                    try:
                        self._proc.terminate()
                    except ProcessLookupError:
                        pass
                    break
                line = await self._proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                if not text:
                    continue
                buf.append(text)
                yield TextChunk(delta=text + "\n")
        finally:
            stderr_task: asyncio.Task | None = None
            stderr_chunks: list[str] = []

            async def _drain_stderr() -> None:
                assert self._proc and self._proc.stderr
                while True:
                    chunk = await self._proc.stderr.read(512)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk.decode("utf-8", errors="replace"))

            stderr_task = asyncio.create_task(_drain_stderr())
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
            if stderr_task and not stderr_task.done():
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

            err_text = "".join(stderr_chunks).strip()
            final = "\n".join(buf).strip() or (
                f"[agent] pi produced no output (exit {self._proc.returncode})."
                + (f" stderr: {err_text}" if err_text else "")
            )
            self._proc = None
            yield Complete(final_text=final)

    async def cancel(self) -> None:
        self._cancel_requested = True
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass

    async def __aenter__(self) -> "PiAdapter":
        return self

    async def __aexit__(self, *a: object) -> None:
        await self.cancel()