#!/bin/bash
# 初始化脚本：下载并解压本地 TTS 模型到 models/。
#
# 用法:
#   scripts/init_models.sh            # 下载默认模型 (fanchen 情感 TTS)
#   scripts/init_models.sh --kokoro  # 追加 Kokoro 中英双语 (103 说话人)
#   scripts/init_models.sh --qwen    # 安装 Qwen3-TTS 1.7B Q4 (情感标签, 97ms 延迟)
#   scripts/init_models.sh --all     # 全部模型都下载
#   scripts/init_models.sh --engine kokoro|fanchen|qwen   # 只下载指定引擎
#
# 环境变量:
#   MODELS_DIR     模型目录 (默认 ./models)
#   FORCE=1        强制重新下载
set -e

if ! command -v curl >/dev/null 2>&1; then
    echo "错误: 需要 curl" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

MODELS_DIR="${MODELS_DIR:-models}"
mkdir -p "$MODELS_DIR"

KOKORO_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_1.tar.bz2"
KOKORO_SIZE=147031220
KOKORO_DIR="kokoro-int8-multi-lang-v1_1"

FANCHEN_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-fanchen-C.tar.bz2"
FANCHEN_SIZE=119326431
FANCHEN_DIR="vits-zh-hf-fanchen-C"

QWEN_MODEL_DIR="qwen3-tts-1.7b"
QWEN_TALKER_URL="https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/resolve/main/qwen-talker-1.7b-customvoice-Q4_K_M.gguf"
QWEN_TALKER_SIZE=$((1200 * 1024 * 1024))
QWEN_TOKENIZER_URL="https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/resolve/main/qwen-tokenizer-12hz-Q4_K_M.gguf"
QWEN_TOKENIZER_SIZE=$((255 * 1024 * 1024))

ADD_KOKORO=0
ADD_QWEN=0
ENGINE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --kokoro) ADD_KOKORO=1 ;;
        --qwen) ADD_QWEN=1 ;;
        --all) ADD_KOKORO=1; ADD_QWEN=1 ;;
        --engine)
            shift
            ENGINE="$1"
            [ "$ENGINE" != "kokoro" ] && [ "$ENGINE" != "fanchen" ] && [ "$ENGINE" != "qwen" ] && {
                echo "错误: --engine 只支持 kokoro|fanchen|qwen" >&2
                exit 1
            }
            ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
    shift
done

fetch() {
    local name="$1" url="$2" size="$3" dir="$4"
    local archive="$MODELS_DIR/$name.tar.bz2"
    if [ -d "$MODELS_DIR/$dir" ] && [ -z "$FORCE" ]; then
        echo "[skip] $name 已存在: $MODELS_DIR/$dir"
        return 0
    fi
    local cur=0
    [ -f "$archive" ] && cur=$(stat -c %s "$archive" 2>/dev/null || echo 0)
    if [ "$cur" -ge "$((size / 2))" ]; then
        echo "[resume] $name 断点续传 ($cur/$size bytes)..."
    elif [ -f "$archive" ]; then
        rm -f "$archive"
        echo "[redownload] $name 压缩包损坏，重新下载..."
    else
        echo "[download] $name ($size bytes)..."
    fi
    for i in 1 2 3 4 5; do
        curl -L -C - --connect-timeout 15 --retry 5 --retry-delay 2 \
            -o "$archive" "$url" && break
        echo "[retry] $name 第 $i 次重试..."
        sleep 3
    done
    local final
    final=$(stat -c %s "$archive" 2>/dev/null || echo 0)
    if [ "$final" -lt "$((size / 2))" ]; then
        echo "错误: $name 下载失败 ($final/$size), 请重跑" >&2
        exit 1
    fi
    echo "[extract] $name 解压..."
    tar xf "$archive" -C "$MODELS_DIR"
    rm -f "$archive"
    echo "[done] $name -> $MODELS_DIR/$dir"
}

fetch_qwen() {
    mkdir -p "$MODELS_DIR/$QWEN_MODEL_DIR"
    local talker_file="$MODELS_DIR/$QWEN_MODEL_DIR/qwen-talker-1.7b-customvoice-Q4_K_M.gguf"
    local tokenizer_file="$MODELS_DIR/$QWEN_MODEL_DIR/qwen-tokenizer-12hz-Q4_K_M.gguf"

    if [ -f "$talker_file" ] && [ -f "$tokenizer_file" ] && [ -z "$FORCE" ]; then
        echo "[skip] Qwen3-TTS 已存在: $MODELS_DIR/$QWEN_MODEL_DIR"
        return 0
    fi

    echo "[download] Qwen3-TTS talker (Q4_K_M, ~1.2GB)..."
    for i in 1 2 3 4 5; do
        curl -L -C - --connect-timeout 15 --retry 5 --retry-delay 2 \
            -o "$talker_file" "$QWEN_TALKER_URL" && break
        echo "[retry] talker 第 $i 次重试..."
        sleep 3
    done

    echo "[download] Qwen3-TTS tokenizer (~255MB)..."
    for i in 1 2 3 4 5; do
        curl -L -C - --connect-timeout 15 --retry 5 --retry-delay 2 \
            -o "$tokenizer_file" "$QWEN_TOKENIZER_URL" && break
        echo "[retry] tokenizer 第 $i 次重试..."
        sleep 3
    done

    echo "[done] Qwen3-TTS -> $MODELS_DIR/$QWEN_MODEL_DIR"
}

# 默认: fanchen(情感 TTS, 187 情绪说话人, RTF~0.4 实时 2.5 倍)
# --kokoro/--all: 追加 Kokoro(中英双语, 103 说话人)
# --qwen/--all: Qwen3-TTS 1.7B Q4 (情感标签, 97ms 延迟, CPU 实时)
# --engine kokoro: 只装 Kokoro
# --engine fanchen: 只装 fanchen
# --engine qwen: 只装 Qwen3-TTS
if [ "$ENGINE" = "kokoro" ]; then
    fetch "kokoro-int8-multi-lang-v1_1" "$KOKORO_URL" "$KOKORO_SIZE" "$KOKORO_DIR"
elif [ "$ENGINE" = "fanchen" ]; then
    fetch "vits-zh-hf-fanchen-C" "$FANCHEN_URL" "$FANCHEN_SIZE" "$FANCHEN_DIR"
elif [ "$ENGINE" = "qwen" ]; then
    fetch_qwen
else
    fetch "vits-zh-hf-fanchen-C" "$FANCHEN_URL" "$FANCHEN_SIZE" "$FANCHEN_DIR"
    if [ "$ADD_KOKORO" = "1" ]; then
        if [ ! -d "$MODELS_DIR/$KOKORO_DIR" ]; then
            echo "[info] 同时安装 Kokoro 作为双语备选..."
            fetch "kokoro-int8-multi-lang-v1_1" "$KOKORO_URL" "$KOKORO_SIZE" "$KOKORO_DIR"
        else
            echo "[skip] Kokoro 已存在，跳过（可用 --engine kokoro 强制重装）"
        fi
    fi
    if [ "$ADD_QWEN" = "1" ]; then
        if [ ! -d "$MODELS_DIR/$QWEN_MODEL_DIR" ]; then
            echo "[info] 同时安装 Qwen3-TTS..."
            fetch_qwen
        else
            echo "[skip] Qwen3-TTS 已存在"
        fi
    fi
fi

echo ""
echo "模型就绪:"
ls -d "$MODELS_DIR"/*/ 2>/dev/null || true
echo ""
echo "现在启动: scripts/start.sh"
