"""Claude CodeのStop hookエントリポイント.

stdinからhookイベントのJSONを受け取り、transcriptを解析して
ObsidianにMarkdownノートとして保存する。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_obsidian_hook.config import OBSIDIAN_CLI, OBSIDIAN_HISTORY_PATH
from claude_obsidian_hook.transcript import (
    extract_messages,
    extract_metadata,
    format_as_markdown,
    parse_transcript,
)

logger = logging.getLogger(__name__)


def _read_hook_input() -> dict:
    """stdinからhookイベントのJSONを読み込む.

    Returns:
        パースされたhookイベントの辞書.
    """
    return json.loads(sys.stdin.read())


def _escape_for_obsidian(content: str) -> str:
    """Obsidian CLIのcontentパラメータ用にエスケープする.

    改行を ``\\n`` リテラルに変換する。

    Args:
        content: エスケープ対象の文字列.

    Returns:
        エスケープ済み文字列.
    """
    return content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _generate_timestamp_filename() -> str:
    """現在時刻からファイル名用のタイムスタンプを生成する.

    Returns:
        ``YYYY-MM-DD_HH-MM-SS`` 形式の文字列.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d_%H-%M-%S")


def _save_to_obsidian(note_path: str, content: str) -> None:
    """Obsidian CLIでノートを作成する.

    Args:
        note_path: Obsidian vault内のノートパス.
        content: ノートの内容.
    """
    escaped = _escape_for_obsidian(content)
    subprocess.run(
        [
            OBSIDIAN_CLI,
            "create",
            f"path={note_path}",
            f"content={escaped}",
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )


def _launch_reflect(
    transcript_path: str,
    session_id: str,
    obsidian_history_path: str,
) -> None:
    """reflect.pyをバックグラウンドプロセスとして起動する.

    Args:
        transcript_path: transcriptファイルのパス.
        session_id: セッションID.
        obsidian_history_path: Obsidianに保存したノートのパス.
    """
    project_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get(
        "CLAUDE_OBSIDIAN_HOOK_ROOT"
    )
    cwd = Path(project_root) if project_root else None
    env = {**os.environ, "CLAUDE_SKIP_ANALYSIS": "1"}
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_obsidian_hook.reflect",
            transcript_path,
            session_id,
            obsidian_history_path,
        ],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def main() -> None:
    """Stop hookのメインエントリポイント."""
    logging.basicConfig(level=logging.INFO)

    # 無限ループ防止: 振り返り生成セッション自身のStop hookをスキップする
    if os.getenv("CLAUDE_SKIP_ANALYSIS") == "1":
        sys.exit(0)

    hook_input = _read_hook_input()

    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "")

    if not transcript_path:
        logger.error("transcript_pathが指定されていません。")
        sys.exit(0)

    try:
        # transcript解析
        records = parse_transcript(transcript_path)
        messages = extract_messages(records)
        metadata = extract_metadata(records)
        markdown = format_as_markdown(messages, metadata)

        # Obsidianに保存
        timestamp = _generate_timestamp_filename()
        obsidian_path = f"{OBSIDIAN_HISTORY_PATH}/{timestamp}.md"
        _save_to_obsidian(obsidian_path, markdown)

        # reflect.pyをバックグラウンドで起動
        _launch_reflect(transcript_path, session_id, obsidian_path)
    except Exception:
        logger.exception("hook処理中にエラーが発生しました")

    sys.exit(0)


if __name__ == "__main__":
    main()
