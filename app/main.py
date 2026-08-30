from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
import json
import os

from app.web.ws_endpoint import ws_endpoint

app = FastAPI()

AVATARS_DIR = "app/web/static/avatars"
SETTING_KEYS = ("baseUrl", "apiKey", "model")


def _settings_path() -> str:
    return os.environ.get("VOICE_SHELL_SETTINGS", "settings.local.json")


def _load_settings() -> dict:
    data = {k: "" for k in SETTING_KEYS}
    path = _settings_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            for k in SETTING_KEYS:
                data[k] = str(stored.get(k, "") or "").strip()
        except Exception:
            pass
    return data


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api/avatars")
async def list_avatars():
    """Scan static/avatars/*/ and return available digital-human assets."""
    avatars = []
    if os.path.isdir(AVATARS_DIR):
        for name in sorted(os.listdir(AVATARS_DIR)):
            dir_path = os.path.join(AVATARS_DIR, name)
            if not os.path.isdir(dir_path):
                continue
            sheets = sorted(
                f for f in os.listdir(dir_path)
                if f.lower().endswith((".webp", ".png", ".gif", ".jpg"))
            )
            if not sheets:
                continue
            meta = {}
            meta_path = os.path.join(dir_path, "meta.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}
            avatars.append({"name": name, "sheet": sheets[0], "meta": meta})
    return {"avatars": avatars}


@app.post("/api/avatars/{name}/meta")
async def save_avatar_meta(name: str, request: Request):
    """Persist meta.json for an avatar (e.g. detected colsByRow)."""
    if not name or "/" in name or ".." in name:
        return JSONResponse({"error": "invalid name"}, status_code=400)
    dir_path = os.path.join(AVATARS_DIR, name)
    if not os.path.isdir(dir_path):
        return JSONResponse({"error": "avatar not found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    meta_path = os.path.join(dir_path, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)
    return {"ok": True, "path": f"static/avatars/{name}/meta.json"}


@app.get("/api/settings")
async def get_settings():
    return _load_settings()


@app.post("/api/settings")
async def save_settings(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    data = {}
    for k in SETTING_KEYS:
        data[k] = str(body.get(k, "") or "").strip()
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True}


app.websocket("/ws")(ws_endpoint)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
