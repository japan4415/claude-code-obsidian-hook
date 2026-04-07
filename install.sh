#!/usr/bin/env bash
set -euo pipefail

# Claude Code Obsidian Hook インストールスクリプト
# 使い方: bash install.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
OBSIDIAN_CLI="/usr/local/bin/obsidian"

echo "=== Claude Code Obsidian Hook インストール ==="
echo "プロジェクトディレクトリ: $SCRIPT_DIR"

# 1. uv sync で依存をインストール
echo ""
echo "[1/4] 依存パッケージをインストール中..."
cd "$SCRIPT_DIR"
uv sync
echo "  -> 完了"

# 2. settings.json にStop hookを追加
echo ""
echo "[2/4] Claude Code settings.json にStop hookを設定中..."

HOOK_COMMAND="cd '${SCRIPT_DIR}' && uv run python -m claude_obsidian_hook.save"
NEW_HOOK_ENTRY=$(cat <<HOOKEOF
{
  "hooks": [
    {
      "type": "command",
      "command": "$HOOK_COMMAND",
      "timeout": 15
    }
  ]
}
HOOKEOF
)

mkdir -p "$(dirname "$SETTINGS_FILE")"

# settings.json が無ければ空オブジェクトで初期化
if [ ! -f "$SETTINGS_FILE" ]; then
    echo "{}" > "$SETTINGS_FILE"
fi

# jq があれば jq を使用、なければ Python でフォールバック
if command -v jq &> /dev/null; then
    _merge_with_jq() {
        local tmp
        tmp=$(mktemp)
        jq --argjson new_entry "$NEW_HOOK_ENTRY" '
            # hooks オブジェクトが無ければ初期化
            .hooks //= {} |
            # 既存のStop配列を取得（無ければ空配列）
            (.hooks.Stop // []) as $existing_stops |
            # 新しいhookのcommandを取得
            ($new_entry.hooks[0].command) as $new_cmd |
            # 同じcommandが既に存在するかチェック
            ([$existing_stops[] | select(.hooks[]?.command == $new_cmd)] | length > 0) as $already_exists |
            # Stop配列だけを更新（他のhookイベントには触れない）
            if $already_exists then
                .
            else
                .hooks.Stop = ($existing_stops + [$new_entry])
            end
        ' "$SETTINGS_FILE" > "$tmp"
        mv "$tmp" "$SETTINGS_FILE"
    }
    _merge_with_jq
else
    _merge_with_python() {
        python3 - "$SETTINGS_FILE" "$HOOK_COMMAND" <<'PYEOF'
import json
import sys

settings_path = sys.argv[1]
hook_command = sys.argv[2]

with open(settings_path, encoding="utf-8") as f:
    settings = json.load(f)

new_hook_entry = {
    "hooks": [
        {
            "type": "command",
            "command": hook_command,
            "timeout": 15,
        }
    ]
}

hooks = settings.setdefault("hooks", {})
stop_hooks = hooks.setdefault("Stop", [])

# 同じcommandが既に存在するかチェック
already_exists = any(
    h.get("command") == hook_command
    for entry in stop_hooks
    for h in entry.get("hooks", [])
)

if not already_exists:
    stop_hooks.append(new_hook_entry)

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
    }
    _merge_with_python
fi

echo "  -> 完了"

# 3. Obsidianにreflections.mdを初期化（既に存在する場合はスキップ）
echo ""
echo "[3/4] Obsidian reflections.md を確認中..."

if [ -x "$OBSIDIAN_CLI" ]; then
    if ! "$OBSIDIAN_CLI" read path="coding/reflections.md" &> /dev/null; then
        "$OBSIDIAN_CLI" create path="coding/reflections.md" \
            content="# 振り返りログ\n\nセッションごとの教訓を蓄積する。\n"
        echo "  -> coding/reflections.md を作成しました"
    else
        echo "  -> coding/reflections.md は既に存在します（スキップ）"
    fi
else
    echo "  -> obsidian CLI が見つかりません。reflections.md の作成をスキップします。"
    echo "     手動で作成してください: obsidian create path=\"coding/reflections.md\" content=\"# 振り返りログ\""
fi

# 4. 完了メッセージ
echo ""
echo "[4/4] インストール完了!"
echo ""
echo "=== セットアップ完了 ==="
echo "Claude Codeのセッション終了時に自動で振り返りが生成されます。"
echo ""
echo "設定ファイル: $SETTINGS_FILE"
echo "ログファイル:  ~/.claude/logs/obsidian-hook.log"
