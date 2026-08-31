import asyncio
import json
import os
import re
import shlex
import sys
from typing import AsyncIterator

from app.agent.base import AgentClient
from app.events.events import Complete, TextChunk, VoiceEvent

RUNTIME_SETTING_KEYS = ("baseUrl", "apiKey", "model")

PROVIDER_ID = "voice-shell"
CUSTOM_MODEL_ID = "main"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
API_KEY_ENV = "VOICE_SHELL_API_KEY"


def _settings_path() -> str:
    return os.environ.get("VOICE_SHELL_SETTINGS", "settings.local.json")


def _load_runtime_settings() -> dict:
    """Read runtime model settings written by the UI (GET/POST /api/settings)."""
    data = {k: "" for k in RUNTIME_SETTING_KEYS}
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            stored = json.load(f)
        for k in RUNTIME_SETTING_KEYS:
            data[k] = str(stored.get(k, "") or "").strip()
    except Exception:
        pass
    return data


def _models_json_path() -> str:
    return os.environ.get(
        "PI_MODELS_JSON", os.path.expanduser("~/.pi/agent/models.json")
    )


def upsert_custom_provider(cfg: dict) -> bool:
    """Register the user's OpenAI-compatible endpoint as a dedicated `voice-shell`
    provider in pi's models.json.

    pi resolves custom endpoints through models.json providers (there is no
    base-URL flag or env var). A dedicated provider keeps the user's own
    openai/anthropic/etc. configuration untouched. The API key is referenced as
    $VOICE_SHELL_API_KEY and injected into the pi subprocess environment, so no
    secret is ever written to models.json. Returns True when a custom endpoint
    is configured, False to keep pi on its default setup.
    """
    if not (cfg.get("baseUrl") or cfg.get("model")):
        return False
    model_id = cfg.get("model") or CUSTOM_MODEL_ID
    entry = {
        "name": "Voice Shell Provider",
        "baseUrl": cfg.get("baseUrl") or DEFAULT_OPENAI_BASE_URL,
        "api": "openai-completions",
        "models": [
            {
                "id": model_id,
                "name": model_id,
                "reasoning": False,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": 128000,
                "maxTokens": 8192,
            }
        ],
    }
    if cfg.get("apiKey"):
        # Keep the secret out of models.json on disk — pi resolves $VAR refs
        # at request time from the subprocess environment.
        entry["apiKey"] = f"${API_KEY_ENV}"
    path = _models_json_path()
    store = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                store = json.load(f)
        except Exception:
            # Keep a backup rather than silently dropping the user's config.
            try:
                with open(path + ".bak", "w", encoding="utf-8") as f:
                    f.write(open(path, "r", encoding="utf-8", errors="replace").read())
            except Exception:
                pass
            store = {}
    if not isinstance(store, dict):
        store = {}
    providers = store.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = store["providers"] = {}
    providers[PROVIDER_ID] = entry
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return True


class _ThinkFilter:
    """Strips model-emitted think blocks from the stream.

    Some models (e.g. MiniMax via an OpenAI-compatible endpoint) emit bare
    `think` / `think` tags inline in the content instead of a separate
    reasoning channel. The filter is streaming-aware: it holds back partial
    tags at the buffer boundary so tags split across chunks are still removed.
    """

    # MiniMax emits both bare `think`/`think` and bracketed `think`/`think`
    # tags depending on the run — support both.
    _OPEN = re.compile(r"(?:^|(?<=\n))(?:<think|think)")
    # The close tag must also be at line start (mirroring OPEN) — otherwise a
    # bare `think` inside the reasoning text (e.g. "I think about this") would
    # prematurely terminate the think block and leak reasoning into the answer.
    _CLOSE = re.compile(r"(?:^|(?<=\n))think|</?think>")
    _OPEN_CANDIDATES = ("think", "<think")
    _MAX_HOLD = 8000

    def __init__(self) -> None:
        self._in_think = False
        self._hold = ""
        self._saw_text = False

    def _emit(self, part: str) -> str:
        """Drop leading whitespace until the first real character (the think
        block usually leaves a run of newlines before the answer)."""
        if not self._saw_text:
            part = part.lstrip()
            if part.strip():
                self._saw_text = True
        return part

    @classmethod
    def _partial_open(cls, s: str) -> str:
        """Longest suffix of s that could be the start of an open tag."""
        for length in range(min(len(s), 8), 0, -1):
            suffix = s[-length:]
            if any(c.startswith(suffix) for c in cls._OPEN_CANDIDATES):
                return suffix
        return ""

    def feed(self, text: str) -> str:
        data = self._hold + text
        self._hold = ""
        out: list[str] = []
        while True:
            if self._in_think:
                m = self._CLOSE.search(data)
                if m:
                    data = data[m.end():]
                    self._in_think = False
                elif len(data) >= self._MAX_HOLD:
                    # No close tag in sight — stop swallowing the answer.
                    self._in_think = False
                    out.append(self._emit(data))
                    data = ""
                else:
                    self._hold = data
                    return "".join(out)
            else:
                m = self._OPEN.search(data)
                if m:
                    out.append(self._emit(data[: m.start()]))
                    data = data[m.end():]
                    self._in_think = True
                    continue
                partial = self._partial_open(data)
                out.append(self._emit(data[: len(data) - len(partial)]))
                self._hold = partial
                return "".join(out)

    def flush(self) -> str:
        held, self._hold = self._hold, ""
        return self._emit(held)


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
            # JSON mode (NDJSON) is required for real token-level streaming:
            # text mode buffers the whole reply (it is a single line) and
            # emits it all at once.
            "--mode", "json",
            "--no-session",
            "--no-tools",
            "--thinking", "off",
        ]

        env = os.environ.copy()
        cfg = _load_runtime_settings()
        if upsert_custom_provider(cfg):
            cmd.extend(
                ["--provider", PROVIDER_ID, "--model", cfg["model"] or CUSTOM_MODEL_ID]
            )
            if cfg["apiKey"]:
                env[API_KEY_ENV] = cfg["apiKey"]

        extra_args = os.environ.get("PI_ARGS")
        if extra_args:
            cmd.extend(shlex.split(extra_args))

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
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
        think = _ThinkFilter()
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
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                text = ""
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict):
                    if obj.get("type") == "message_update":
                        ame = obj.get("assistantMessageEvent") or {}
                        if ame.get("type") == "text_delta":
                            text = ame.get("delta") or ""
                    # other events (session/turn/message lifecycle) are ignored
                else:
                    # Non-JSON line on stdout — treat as raw text.
                    text = raw
                if not text:
                    continue
                filtered = think.feed(text)
                if not filtered.strip():
                    continue
                buf.append(filtered)
                yield TextChunk(delta=filtered)
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

            tail = think.flush()
            if tail.strip():
                buf.append(tail)
            err_text = "".join(stderr_chunks).strip()
            final = "".join(buf).strip() or (
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