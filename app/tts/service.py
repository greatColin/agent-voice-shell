"""本地 TTS 服务，支持多引擎并发合成。

多引擎抽象：
  - qwen:    Qwen3-TTS 1.7B Q4（情感标签 + 自然语言指令，CPU 实时）
  - vits:    VITS zh-hf-fanchen（187 情绪说话人，RTF 0.4 最快）
  - kokoro:  Kokoro multi-lang v1.1（103 说话人，中英双语）

并发合成：
  - 线程池（默认 2 workers）并行处理多个合成请求
  - 结果按提交顺序入队，WS 串行 pull，保证语音和文字同步

模型目录由环境变量 VOICE_SHELL_MODELS_DIR 指定（默认 ./models）。
"""

import asyncio
import base64
import os
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import Optional

try:
    import sherpa_onnx

    _SHERPA_AVAILABLE = True
except ImportError:
    sherpa_onnx = None
    _SHERPA_AVAILABLE = False

MODELS_DIR = os.environ.get(
    "VOICE_SHELL_MODELS_DIR", os.path.join(os.getcwd(), "models")
)

KOKORO_VOICES = [
    (45, "zf_xiaobei", "小北 · 中文女声"),
    (46, "zf_xiaoni", "小妮 · 中文女声"),
    (47, "zf_xiaoxiao", "晓晓 · 中文女声"),
    (48, "zf_xiaoyi", "小艺 · 中文女声"),
    (49, "zm_yunjian", "云健 · 中文男声"),
    (50, "zm_yunxi", "云希 · 中文男声"),
    (51, "zm_yunxia", "云夏 · 中文女声"),
    (52, "zm_yunyang", "云扬 · 中文男声"),
]

FANCHEN_EMOTIONS = ["开心", "生气", "悲伤", "平静", "惊讶", "害怕"]


class TtsEngine(Enum):
    QWEN = "qwen"
    VITS = "vits"
    KOKORO = "kokoro"


@dataclass
class QueuedTtsResult:
    seq: int
    text: str
    wav_b64: str
    sample_rate: int


class TtsUnavailable(Exception):
    pass


class TtsService:
    _instance: Optional["TtsService"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._engine: Optional[TtsEngine] = None
        self._model_dir: Optional[str] = None
        self._voice_ids: dict = {}
        self._tts: Optional[object] = None
        self._qwen_model = None
        self._load_error: Optional[str] = None
        self._sherpa_lock = threading.RLock()

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts-")

        self._qwen_available = False
        try:
            from qwen_tts import QwenTTS

            self._QwenTTS = QwenTTS
            self._qwen_available = True
        except ImportError:
            self._qwen_available = False

    @classmethod
    def get_instance(cls) -> "TtsService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def status(self) -> dict:
        ready = self._tts is not None or self._qwen_model is not None
        voices = []
        if ready:
            voices = [
                {"id": str(vid), "name": name, "label": label}
                for vid, name, label in self._voice_ids.values()
            ]
        return {
            "available": _SHERPA_AVAILABLE or self._qwen_available,
            "ready": ready,
            "engine": self._engine.value if self._engine else None,
            "model_dir": self._model_dir,
            "sample_rate": 24000 if self._engine == TtsEngine.QWEN else (
                self._tts.sample_rate if self._tts else None
            ),
            "voices": voices,
            "error": self._load_error,
        }

    def _discover_model(self):
        if not os.path.isdir(MODELS_DIR):
            return None, None
        candidates = []
        for entry in sorted(os.listdir(MODELS_DIR)):
            full = os.path.join(MODELS_DIR, entry)
            if not os.path.isdir(full):
                continue
            name = entry.lower()
            if "qwen" in name or "cosyvoice" in name:
                candidates.append((TtsEngine.QWEN, full))
            elif "kokoro" in name:
                candidates.append((TtsEngine.KOKORO, full))
            elif "fanchen" in name or "vits" in name:
                if any(f.endswith(".onnx") for f in os.listdir(full)):
                    candidates.append((TtsEngine.VITS, full))
        for engine, full in candidates:
            if engine == TtsEngine.QWEN:
                return engine, full
        for engine, full in candidates:
            if engine == TtsEngine.VITS:
                return engine, full
        return candidates[0] if candidates else (None, None)

    def _ensure_loaded(self):
        with self._sherpa_lock:
            if self._tts is not None:
                return
            if not _SHERPA_AVAILABLE:
                self._load_error = "sherpa-onnx 未安装"
                raise TtsUnavailable(self._load_error)
            engine, model_dir = self._discover_model()
            if engine is None:
                self._load_error = f"未找到 TTS 模型: {MODELS_DIR}"
                raise TtsUnavailable(self._load_error)
            if engine != TtsEngine.VITS and engine != TtsEngine.KOKORO:
                self._load_error = f"未识别引擎: {engine}"
                raise TtsUnavailable(self._load_error)
            try:
                if engine == TtsEngine.KOKORO:
                    self._tts = self._create_kokoro(model_dir)
                else:
                    self._tts = self._create_vits(model_dir)
                self._engine = engine
                self._model_dir = model_dir
            except Exception as e:
                self._load_error = f"模型加载失败: {e}"
                raise TtsUnavailable(self._load_error)

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

    def _synth_sherpa(self, text: str, voice: str, speed: float) -> bytes:
        with self._sherpa_lock:
            self._ensure_loaded()
            tts = self._tts
            sid = int(voice) if voice in self._voice_ids else None
            if sid is None:
                sid = 47 if self._engine == TtsEngine.KOKORO else 0
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

    def _synthesize_qwen(self, text: str, voice: str, speed: float) -> bytes:
        if self._qwen_model is None:
            model_dir = None
            if os.path.isdir(MODELS_DIR):
                for entry in os.listdir(MODELS_DIR):
                    if "qwen" in entry.lower() or "cosyvoice" in entry.lower():
                        model_dir = os.path.join(MODELS_DIR, entry)
                        break
            if model_dir is None:
                raise TtsUnavailable("Qwen3-TTS 模型未找到")
            self._qwen_model = self._QwenTTS.from_pretrained(model_dir)
            self._voice_ids = {"0": (0, "default", "默认音色")}
            self._engine = TtsEngine.QWEN
            self._model_dir = model_dir

        speed_ratio = 1.0 / max(0.5, min(2.0, float(speed)))
        wav = self._qwen_model.synthesize(text, voice=voice or "default")
        if hasattr(wav, "numpy"):
            samples = wav.numpy()
        else:
            samples = wav
        if samples.ndim > 1:
            samples = samples.squeeze(-1) if samples.ndim == 2 else samples.flatten()

        target_sr = 24000
        import numpy as np
        samples = np.clip(samples, -1.0, 1.0)
        int_samples = (samples * 32767).astype(np.int16)

        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(target_sr)
            w.writeframes(int_samples.tobytes())
        return buf.getvalue()

    def _synth_sync(self, seq: int, text: str, voice: str, speed: float) -> QueuedTtsResult:
        if self._engine == TtsEngine.QWEN or (self._engine is None and self._qwen_available):
            wav = self._synthesize_qwen(text, voice, speed)
        else:
            wav = self._synth_sherpa(text, voice, speed)
        wav_b64 = base64.b64encode(wav).decode("ascii")
        return QueuedTtsResult(seq=seq, text=text, wav_b64=wav_b64, sample_rate=24000)

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> asyncio.Queue:
        loop = asyncio.get_event_loop()
        seq = id(text) & 0xFFFF

        completion_queue: asyncio.Queue[Optional[QueuedTtsResult]] = asyncio.Queue(maxsize=1)

        def _worker():
            try:
                result = self._synth_sync(seq, text, voice, speed)
                loop.call_soon_threadsafe(lambda: completion_queue.put_nowait(result))
            except Exception as e:
                loop.call_soon_threadsafe(lambda: completion_queue.put_nowait(None))

        self._executor.submit(_worker)
        return completion_queue

    async def synthesize_sequential(
        self, texts: list[str], voice: str = "", speed: float = 1.0
    ) -> list[asyncio.Queue]:
        return [await self.synthesize(t, voice, speed) for t in texts]


service = TtsService()
