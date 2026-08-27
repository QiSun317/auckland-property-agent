#!/bin/bash
# 为 Cloudflare 免费计划裁剪 LangChain Core 的 Pyodide 产物。
# 项目不启用 LangSmith 远程追踪；用最小兼容层保留 LangChain 的消息、
# ChatModel、Runnable 和 StructuredTool 能力，并删除只在 LangSmith 客户端
# 或类型检查阶段使用的大体积依赖。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_MODULES="$PROJECT_DIR/python_modules"
STUBS_DIR="$PROJECT_DIR/stubs"

copy_stub() {
    local name="$1"
    local source="$STUBS_DIR/${name}-stub/src/$name"
    if [ ! -d "$source" ]; then
        echo "缺少 Pyodide 存根：$source" >&2
        exit 1
    fi
    rm -rf "$PYTHON_MODULES/$name"
    cp -R "$source" "$PYTHON_MODULES/"
}

if [ ! -d "$PYTHON_MODULES/langchain_core" ]; then
    echo "请先运行 uv run pywrangler sync" >&2
    exit 1
fi

rm -rf \
    "$PYTHON_MODULES/langsmith" \
    "$PYTHON_MODULES/anyio" \
    "$PYTHON_MODULES/certifi" \
    "$PYTHON_MODULES/charset_normalizer" \
    "$PYTHON_MODULES/distro" \
    "$PYTHON_MODULES/httpcore" \
    "$PYTHON_MODULES/httpx" \
    "$PYTHON_MODULES/idna" \
    "$PYTHON_MODULES/orjson" \
    "$PYTHON_MODULES/requests" \
    "$PYTHON_MODULES/requests_toolbelt" \
    "$PYTHON_MODULES/sniffio" \
    "$PYTHON_MODULES/urllib3" \
    "$PYTHON_MODULES/websockets" \
    "$PYTHON_MODULES/xxhash" \
    "$PYTHON_MODULES/zstandard"

rm -rf \
    "$PYTHON_MODULES"/anyio-*.dist-info \
    "$PYTHON_MODULES"/certifi-*.dist-info \
    "$PYTHON_MODULES"/charset_normalizer-*.dist-info \
    "$PYTHON_MODULES"/distro-*.dist-info \
    "$PYTHON_MODULES"/httpcore-*.dist-info \
    "$PYTHON_MODULES"/httpx-*.dist-info \
    "$PYTHON_MODULES"/idna-*.dist-info \
    "$PYTHON_MODULES"/orjson-*.dist-info \
    "$PYTHON_MODULES"/requests-*.dist-info \
    "$PYTHON_MODULES"/requests_toolbelt-*.dist-info \
    "$PYTHON_MODULES"/sniffio-*.dist-info \
    "$PYTHON_MODULES"/urllib3-*.dist-info \
    "$PYTHON_MODULES"/websockets-*.dist-info \
    "$PYTHON_MODULES"/xxhash-*.dist-info \
    "$PYTHON_MODULES"/zstandard-*.dist-info

copy_stub "langsmith"
copy_stub "requests"
copy_stub "uuid_utils"

find "$PYTHON_MODULES" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PYTHON_MODULES" -type f \( -name "*.pyc" -o -name "*.pyi" -o -name "RECORD" \) -delete
rm -rf "$PYTHON_MODULES/js-stubs"

echo "LangChain Core Pyodide 产物已裁剪。"
