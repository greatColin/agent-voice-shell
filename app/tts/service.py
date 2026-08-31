"""sherpa-onnx 本地 TTS 服务。

多引擎抽象：
  - kokoro: Kokoro multi-lang v1.1 (103 说话人, 中英双语, int8 量化)
  - vits:   VITS zh-hf-fanchen (187 情绪说话人, 中文情感)

模型目录由环境变量 VOICE_SHELL_MODELS_DIR 指定（默认 ./models），
由 scripts/init_models.sh 负责下载解压。模型未就绪时服务返回
ready=False，前端回退浏览器 TTS。
"""

import asyncio
import os
import threading
import wave
from io import BytesIO

try:
    import sherpa_onnx
    _SHERPA_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖未装时的降级路径
    sherpa_onnx = None
    _SHERPA_AVAILABLE = False

MODELS_DIR = os.environ.get(
    "VOICE_SHELL_MODELS_DIR", os.path.join(os.getcwd(), "models")
)

# Kokoro 说话人（v1.1, id -> 名称/风格）。前缀: zf=中文女声 zm=中文男声
KOKORO_VOICES = [
    (45, "zf_xiaobei", "小北 · 中文女声"),
    (46, "zf_xiaoni", "小妮 · 中文女声"),
    (47, "zf_xiaoxiao", "晓晓 · 中文女声"),
    (48, "zf_xiaoyi", "小艺 · 中文女声"),
    (49, "zm_yunjian", "云健 · 中文男声"),
    (50, "zm_yunxi", "云希 · 中文男声"),
    (51, "zm_yunxia", "云夏 · 中文男声"),
    (52, "zm_yunyang", "云扬 · 中文男声"),
]

# fanchen VITS 情绪标签（187 说话人按情绪分组的引导标签）
FANCHEN_EMOTIONS = ["开心", "生气", "悲伤", "平静", "惊讶", "害怕"]


class TtsUnavailable(Exception):
    pass


class TtsService:
    """sherpa-onnx TTS 单例。synthesize 为 CPU 密集操作，需在线程池执行。"""

    def __init__(self):
        self._tts = None          # sherpa_onnx.OfflineTts
        self._engine = None       # "kokoro" | "vits"
        self._model_dir = None
        self._voice_ids = {}      # voice id -> label
        self._lock = threading.RLock()
        self._load_error = None

    # -- 状态 --------------------------------------------------------------

    def status(self) -> dict:
        ready = self._tts is not None
        voices = []
        if ready:
            voices = [
                {"id": str(vid), "name": name, "label": label}
                for vid, name, label in self._voice_ids.values()
            ]
        return {
            "available": _SHERPA_AVAILABLE,
            "ready": ready,
            "engine": self._engine,
            "model_dir": self._model_dir,
            "sample_rate": self._tts.sample_rate if ready else None,
            "voices": voices,
            "error": self._load_error,
        }

    def _discover_model(self):
        """在 MODELS_DIR 下扫描已解压的模型目录，返回 (engine, dir)。"""
        if not os.path.isdir(MODELS_DIR):
            return None, None
        candidates = []
        for entry in sorted(os.listdir(MODELS_DIR)):
            full = os.path.join(MODELS_DIR, entry)
            if not os.path.isdir(full):
                continue
            name = entry.lower()
            has_onnx = any(
                f.endswith(".onnx") for f in os.listdir(full)
            )
            if not has_onnx:
                continue
            if "kokoro" in name:
                candidates.append(("kokoro", full))
            elif "fanchen" in name or "vits" in name:
                candidates.append(("vits", full))
        # 优先级: vits(fanchen, 情感) > kokoro
        for engine, full in candidates:
            if engine == "vits":
                return engine, full
        return candidates[0] if candidates else (None, None)

    def _ensure_loaded(self):
        """同步加载（线程池内调用），失败时抛 TtsUnavailable。"""
        with self._lock:
            if self._tts is not None:
                return
            if not _SHERPA_AVAILABLE:
                self._load_error = "sherpa-onnx 未安装: pip install sherpa-onnx"
                raise TtsUnavailable(self._load_error)
            engine, model_dir = self._discover_model()
            if engine is None:
                self._load_error = (
                    f"未找到 TTS 模型目录: {MODELS_DIR} 下没有 kokoro*/vits* 模型。"
                    "请运行 scripts/init_models.sh 下载。"
                )
                raise TtsUnavailable(self._load_error)
            try:
                if engine == "kokoro":
                    self._tts = self._create_kokoro(model_dir)
                else:
                    self._tts = self._create_vits(model_dir)
                self._engine = engine
                self._model_dir = model_dir
            except Exception as e:
                self._load_error = f"模型加载失败({model_dir}): {e}"
                raise TtsUnavailable(self._load_error)

    # -- 引擎工厂 ----------------------------------------------------------

    def _create_kokoro(self, d: str):
        lexicon = ",".join([
            os.path.join(d, "lexicon-us-en.txt"),
            os.path.join(d, "lexicon-zh.txt"),
        ])
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=os.path.join(d, "model.int8.onnx"),
                    voices=os.path.join(d, "voices.bin"),
                    tokens=os.path.join(d, "tokens.txt"),
                    lexicon=lexicon,
                    data_dir=os.path.join(d, "espeak-ng-data"),
                    dict_dir=os.path.join(d, "dict"),
                    lang="cmn",
                ),
                num_threads=4,
            ),
        )
        tts = sherpa_onnx.OfflineTts(cfg)
        self._voice_ids = {str(vid): (vid, name, label) for vid, name, label in KOKORO_VOICES}
        return tts

    def _create_vits(self, d: str):
        # vits-zh-hf-fanchen 模型目录（导出自 VITS-fast-fine-tuning）
        model_file = next(
            (f for f in os.listdir(d) if f.endswith(".onnx")),
            "model.onnx",
        )
        fsts = ",".join(
            os.path.join(d, f)
            for f in ("phone.fst", "date.fst", "number.fst", "new_heteronym.fst")
            if os.path.isfile(os.path.join(d, f))
        )
        model = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=os.path.join(d, model_file),
            tokens=os.path.join(d, "tokens.txt"),
            lexicon=os.path.join(d, "lexicon.txt"),
        )
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(vits=model, num_threads=4),
            rule_fsts=fsts,
        )
        tts = sherpa_onnx.OfflineTts(cfg)
        n = tts.num_speakers
        self._voice_ids = {}
        for i in range(n):
            label = FANCHEN_EMOTIONS[i % len(FANCHEN_EMOTIONS)] if i < 60 else "情感音色"
            self._voice_ids[str(i)] = (i, f"fanchen-{i}", f"fanchen-{i} · {label}")
        return tts

    # -- 合成 --------------------------------------------------------------

    def _synth_sync(self, text: str, voice: str, speed: float) -> bytes:
        """合成并返回 WAV 字节。"""
        with self._lock:
            self._ensure_loaded()
            tts = self._tts
            sid = int(voice) if voice in self._voice_ids else None
            if sid is None:
                sid = 47 if self._engine == "kokoro" else 0
            speed = max(0.5, min(2.0, float(speed)))
            audio = tts.generate(text, sid=sid, speed=speed)
        if not audio or len(audio.samples) == 0:
            raise TtsUnavailable("合成失败：空输出")
        samples = [int(max(-1.0, min(1.0, s)) * 32767) for s in audio.samples]
        pcm = b"".join(
            (s & 0xFFFF).to_bytes(2, "little", signed=False) for s in samples
        )
        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tts.sample_rate)
            w.writeframes(pcm)
        return buf.getvalue()

    async def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synth_sync, text, voice, speed)


service = TtsService()
