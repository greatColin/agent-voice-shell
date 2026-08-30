import json
import os

import pytest
from fastapi.testclient import TestClient

from app.agent.pi_adapter import PiAdapter, _load_runtime_settings
from app.main import app


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.local.json"
    monkeypatch.setenv("VOICE_SHELL_SETTINGS", str(path))
    return str(path)


class TestLoadRuntimeSettings:
    def test_missing_file_returns_empty(self, settings_file):
        cfg = _load_runtime_settings()
        assert cfg == {"baseUrl": "", "apiKey": "", "model": ""}

    def test_reads_written_settings(self, settings_file):
        with open(settings_file, "w") as f:
            json.dump({"baseUrl": "http://x/v1", "apiKey": "k", "model": "m"}, f)
        cfg = _load_runtime_settings()
        assert cfg == {"baseUrl": "http://x/v1", "apiKey": "k", "model": "m"}

    def test_invalid_json_returns_empty(self, settings_file):
        with open(settings_file, "w") as f:
            f.write("not json {")
        assert _load_runtime_settings() == {"baseUrl": "", "apiKey": "", "model": ""}

    def test_values_are_stripped(self, settings_file):
        with open(settings_file, "w") as f:
            json.dump({"baseUrl": " http://x/v1 ", "apiKey": None, "model": 123}, f)
        cfg = _load_runtime_settings()
        assert cfg["baseUrl"] == "http://x/v1"
        assert cfg["apiKey"] == ""
        assert cfg["model"] == "123"


class TestPiAdapterUsesSettings:
    @pytest.mark.asyncio
    async def test_cmd_and_env_with_settings(self, settings_file, tmp_path, monkeypatch):
        models_json = tmp_path / "models.json"
        models_json.write_text(json.dumps({
            "providers": {"openai": {"baseUrl": "https://api.openai.com/v1", "models": []}}
        }))
        monkeypatch.setenv("PI_MODELS_JSON", str(models_json))
        with open(settings_file, "w") as f:
            json.dump(
                {"baseUrl": "http://127.0.0.1:9799/v1", "apiKey": "sk-test", "model": "my-model"},
                f,
            )
        captured = {}

        class FakeProc:
            stdout = None
            stderr = None
            returncode = 0

        async def fake_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")

            async def readline():
                return b""

            async def read(n):
                return b""

            async def wait(self):
                return 0

            FakeProc.stdout = type("S", (), {"readline": staticmethod(readline)})()
            FakeProc.stderr = type("S", (), {"read": staticmethod(read)})()
            FakeProc.wait = wait
            return FakeProc()

        monkeypatch.setattr(
            "app.agent.pi_adapter._resolve_pi_binary", lambda: "pi-fake"
        )
        monkeypatch.setattr(
            "asyncio.create_subprocess_exec", fake_exec
        )
        adapter = PiAdapter()
        async for ev in adapter.stream([{"role": "user", "content": "hi"}]):
            pass

        cmd = captured["cmd"]
        assert cmd[cmd.index("--provider") + 1] == "voice-shell"
        assert cmd[cmd.index("--model") + 1] == "my-model"
        assert "--api-key" not in cmd
        assert captured["env"]["VOICE_SHELL_API_KEY"] == "sk-test"
        store = json.loads(models_json.read_text())
        prov = store["providers"]["voice-shell"]
        assert prov["baseUrl"] == "http://127.0.0.1:9799/v1"
        assert prov["models"][0]["id"] == "my-model"
        assert "sk-test" not in models_json.read_text()
        assert "openai" in store["providers"]

    @pytest.mark.asyncio
    async def test_no_settings_keeps_default(self, settings_file, monkeypatch):
        captured = {}

        class FakeProc:
            stdout = None
            stderr = None
            returncode = 0

        async def fake_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")

            async def readline():
                return b""

            async def read(n):
                return b""

            async def wait(self):
                return 0

            FakeProc.stdout = type("S", (), {"readline": staticmethod(readline)})()
            FakeProc.stderr = type("S", (), {"read": staticmethod(read)})()
            FakeProc.wait = wait
            return FakeProc()

        monkeypatch.setattr(
            "app.agent.pi_adapter._resolve_pi_binary", lambda: "pi-fake"
        )
        monkeypatch.setattr(
            "asyncio.create_subprocess_exec", fake_exec
        )
        adapter = PiAdapter()
        async for _ in adapter.stream([{"role": "user", "content": "hi"}]):
            pass

        cmd = captured["cmd"]
        assert "--provider" not in cmd
        assert "--model" not in cmd
        assert "--api-key" not in cmd
        assert "VOICE_SHELL_API_KEY" not in captured["env"]


class TestUpsertCustomProvider:
    def test_noop_without_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PI_MODELS_JSON", str(tmp_path / "models.json"))
        from app.agent.pi_adapter import upsert_custom_provider
        assert upsert_custom_provider({"baseUrl": "", "apiKey": "", "model": ""}) is False
        assert not (tmp_path / "models.json").exists()

    def test_creates_store_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PI_MODELS_JSON", str(tmp_path / "models.json"))
        from app.agent.pi_adapter import upsert_custom_provider
        assert upsert_custom_provider({"baseUrl": "http://x/v1", "apiKey": "k", "model": ""}) is True
        store = json.loads((tmp_path / "models.json").read_text())
        assert store["providers"]["voice-shell"]["baseUrl"] == "http://x/v1"

    def test_model_only_uses_default_base_url(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PI_MODELS_JSON", str(tmp_path / "models.json"))
        from app.agent.pi_adapter import upsert_custom_provider
        upsert_custom_provider({"baseUrl": "", "apiKey": "", "model": "my-model"})
        store = json.loads((tmp_path / "models.json").read_text())
        assert store["providers"]["voice-shell"]["baseUrl"] == "https://api.openai.com/v1"
        assert store["providers"]["voice-shell"]["models"][0]["name"] == "my-model"

    def test_preserves_existing_providers(self, tmp_path, monkeypatch):
        models_json = tmp_path / "models.json"
        models_json.write_text(json.dumps({
            "providers": {
                "voice-shell": {"baseUrl": "http://old/v1", "models": []},
                "openai": {"baseUrl": "https://api.openai.com/v1", "models": []},
            }
        }))
        monkeypatch.setenv("PI_MODELS_JSON", str(models_json))
        from app.agent.pi_adapter import upsert_custom_provider
        upsert_custom_provider({"baseUrl": "http://new/v1", "apiKey": "", "model": "m"})
        store = json.loads(models_json.read_text())
        assert store["providers"]["voice-shell"]["baseUrl"] == "http://new/v1"
        assert store["providers"]["openai"]["baseUrl"] == "https://api.openai.com/v1"

    def test_corrupt_store_backed_up(self, tmp_path, monkeypatch):
        models_json = tmp_path / "models.json"
        models_json.write_text("{corrupt")
        monkeypatch.setenv("PI_MODELS_JSON", str(models_json))
        from app.agent.pi_adapter import upsert_custom_provider
        upsert_custom_provider({"baseUrl": "http://x/v1", "apiKey": "", "model": ""})
        assert (tmp_path / "models.json.bak").exists()
        store = json.loads(models_json.read_text())
        assert store["providers"]["voice-shell"]["baseUrl"] == "http://x/v1"


class TestSettingsApi:
    def setup_method(self):
        self.client = TestClient(app)

    def test_get_empty_defaults(self, settings_file):
        r = self.client.get("/api/settings")
        assert r.status_code == 200
        assert r.json() == {"baseUrl": "", "apiKey": "", "model": ""}

    def test_post_then_get_roundtrip(self, settings_file):
        payload = {"baseUrl": "http://h/v1", "apiKey": "kk", "model": "mm"}
        r = self.client.post("/api/settings", json=payload)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert self.client.get("/api/settings").json() == payload
        with open(settings_file) as f:
            assert json.load(f) == payload

    def test_post_strips_whitespace(self, settings_file):
        r = self.client.post(
            "/api/settings", json={"baseUrl": " http://h/v1 ", "apiKey": " ", "model": ""}
        )
        assert r.status_code == 200
        data = self.client.get("/api/settings").json()
        assert data["baseUrl"] == "http://h/v1"
        assert data["apiKey"] == ""

    def test_post_invalid_json(self, settings_file):
        r = self.client.post(
            "/api/settings",
            content=b"{bad",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
