#!/bin/bash
# 下载 Whisper ASR 模型到 models/whisper/。
# 默认下载 base 模型（74MB），支持 tiny/base/small
#
# 用法:
#   scripts/init_asr_model.sh           # 下载 base (默认)
#   scripts/init_asr_model.sh tiny      # 下载 tiny (39MB, 较快)
#   scripts/init_asr_model.sh small       # 下载 small (227MB, 更准)
#
# 环境变量:
#   MODELS_DIR       模型根目录 (默认 ./models)
#   WHISPER_MODEL   模型大小: tiny|base|small (默认 base)
set -e

if ! command -v curl >/dev/null 2>&1; then
    echo "错误: 需要 curl" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

MODELS_DIR="${MODELS_DIR:-models}"
ASR_DIR="$MODELS_DIR/whisper"
mkdir -p "$ASR_DIR"

MODEL_SIZE="${WHISPER_MODEL:-${1:-base}}"
case "$MODEL_SIZE" in
    tiny) HF_MODEL="Systran/faster-whisper-tiny" ;;
    base) HF_MODEL="Systran/faster-whisper-base" ;;
    small) HF_MODEL="Systran/faster-whisper-small" ;;
    *) echo "错误: 模型只支持 tiny|base|small" >&2; exit 1 ;;
esac

# 用 python 下载（huggingface_hub）
echo "[info] 下载 Whisper $MODEL_SIZE 模型到 $ASR_DIR ..."

python3 - <<EOF
import os
os.makedirs("$ASR_DIR", exist_ok=True)

from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="$HF_MODEL",
    local_dir="$ASR_DIR",
    local_dir_use_symlinks=False,
    ignore_patterns=["*.md", "*.txt", "*.json"],
)
print("done")
EOF

echo ""
echo "[done] Whisper $MODEL_SIZE -> $ASR_DIR"
ls -la "$ASR_DIR/" | head -10
echo ""
echo "启动服务: scripts/start.sh"
