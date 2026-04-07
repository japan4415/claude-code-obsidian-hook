# claude-code-obsidian-hook

Claude CodeのStop hookでセッション履歴をObsidianに自動保存し、振り返りを生成するプラグインです。

セッション終了時に以下を自動で行います:

1. セッションのtranscriptを解析し、Obsidianにノートとして保存
2. バックグラウンドでClaude CLIを使って振り返り（リフレクション）を生成し、Obsidianに追記

## 前提条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — Pythonパッケージマネージャ
- [Obsidian CLI](https://github.com/Acreom/obsidian-cli) — ObsidianをCLIから操作するツール
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) — Claude Code CLI

## インストール

### Plugin Marketplace経由（推奨）

Claude Code Plugin Marketplaceに対応しています。Marketplace経由でインストールすると、`scripts/run_hook.sh` が自動的にStop hookとして登録されます。

### 手動インストール

```bash
git clone https://github.com/japan4415/claude-code-obsidian-hook.git
cd claude-code-obsidian-hook
bash install.sh
```

`install.sh` は以下を行います:

1. `uv sync` で依存パッケージをインストール
2. `~/.claude/settings.json` にStop hookを登録
3. Obsidianに `coding/reflections.md` を初期化（Obsidian CLIが利用可能な場合）

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `OBSIDIAN_CLI` | Obsidian CLIの実行パス | `/usr/local/bin/obsidian` |
| `CLAUDE_CLI` | Claude CLIの実行パス | `/usr/local/bin/claude` |
| `CLAUDE_SKIP_ANALYSIS` | `1` に設定すると振り返り生成をスキップ（再帰防止用） | 未設定 |
| `CLAUDE_PLUGIN_ROOT` | プラグインのインストールディレクトリ（Marketplace用） | — |
| `CLAUDE_PLUGIN_DATA` | プラグインの永続データディレクトリ（Marketplace用） | — |
| `CLAUDE_OBSIDIAN_HOOK_ROOT` | プロジェクトルートパスの上書き | — |

## 使い方

インストール後、特別な操作は不要です。Claude Codeのセッションを終了すると、Stop hookが自動的に発火し:

1. **セッション履歴の保存** — transcriptを解析してObsidianにノートを保存します
2. **振り返りの生成** — Claude CLIを使ってセッション内容を振り返り、教訓をObsidianの `coding/reflections.md` に追記します

振り返り生成を一時的にスキップしたい場合は、環境変数 `CLAUDE_SKIP_ANALYSIS=1` を設定してください。

## 開発

```bash
# 依存パッケージのインストール
uv sync

# テスト実行
uv run pytest

# Lint実行
uv run ruff check .
```

## ライセンス

Apache License 2.0 — 詳細は [LICENSE](LICENSE) を参照してください。
