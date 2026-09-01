"""本地 Whisper ASR 服务（faster-whisper）。

模型在服务启动时预加载，支持中文语音识别。
支持发送 WAV 文件（16kHz mono）或原始 PCM 数据。
"""

import asyncio
import os
import threading
from io import BytesIO

try:
    import numpy as np
except ImportError:
    np = None

try:
    import faster_whisper
    _WHISPER_AVAILABLE = True
except ImportError:
    faster_whisper = None
    _WHISPER_AVAILABLE = False

MODELS_DIR = os.environ.get("VOICE_SHELL_MODELS_DIR", os.path.join(os.getcwd(), "models"))
ASR_MODEL_DIR = os.path.join(MODELS_DIR, "whisper")
ASR_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")


class AsrUnavailable(Exception):
    pass


class AsrService:
    """faster-whisper 单例，eager 加载。"""

    def __init__(self):
        self._model = None
        self._model_size = ASR_MODEL_SIZE
        self._ready = False
        self._error = None
        self._lock = threading.Lock()
        self._load_error = None

    @property
    def ready(self) -> bool:
        return self._ready

    def status(self) -> dict:
        return {
            "available": _WHISPER_AVAILABLE,
            "ready": self._ready,
            "model": self._model_size,
            "error": self._load_error,
        }

    def _ensure_loaded(self):
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            if not _WHISPER_AVAILABLE:
                self._load_error = "faster-whisper 未安装: pip install faster-whisper"
                raise AsrUnavailable(self._load_error)
            if not os.path.isdir(ASR_MODEL_DIR):
                self._load_error = (
                    f"ASR 模型未找到: {ASR_MODEL_DIR}。"
                    "请运行 scripts/init_asr_model.sh 下载。"
                )
                raise AsrUnavailable(self._load_error)
            try:
                self._model = faster_whisper.WhisperModel(
                    self._model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=ASR_MODEL_DIR,
                )
                self._ready = True
            except Exception as e:
                self._load_error = f"ASR 模型加载失败: {e}"
                raise AsrUnavailable(self._load_error)

    def _transcribe_sync(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """同步转写，返回文本。"""
        self._ensure_loaded()
        if np is None:
            raise AsrUnavailable("numpy 未安装")

        if not audio_data:
            return ""

        int16_data = np.frombuffer(audio_data, dtype=np.int16)
        audio_float = int16_data.astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            audio_float,
            language="zh",
            vad_filter=False,
            beam_size=5,
        )
        return "".join(seg.text for seg in segments)

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._transcribe_sync, audio_data, sample_rate
        )

    def load(self):
        """同步预加载（服务启动时调用）。"""
        try:
            self._ensure_loaded()
        except AsrUnavailable:
            pass


service = AsrService()
