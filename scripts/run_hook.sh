#!/usr/bin/env bash
set -euo pipefail

# Plugin Marketplace 用ラッパースクリプト
# ${CLAUDE_PLUGIN_ROOT} でプラグインのインストールディレクトリを参照
# ${CLAUDE_PLUGIN_DATA} で永続データディレクトリを参照

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set}"
PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set}"
VENV_DIR="${PLUGIN_DATA}/venv"

# 初回または pyproject.toml が更新された場合のみ再インストール
if ! diff -q "${PLUGIN_ROOT}/pyproject.toml" "${PLUGIN_DATA}/pyproject.toml.cache" >/dev/null 2>&1; then
    uv venv "${VENV_DIR}"
    uv pip install --python "${VENV_DIR}/bin/python" "${PLUGIN_ROOT}"
    cp "${PLUGIN_ROOT}/pyproject.toml" "${PLUGIN_DATA}/pyproject.toml.cache"
fi

# hook を実行（stdinをそのまま渡す）
"${VENV_DIR}/bin/python" -m claude_obsidian_hook.save
