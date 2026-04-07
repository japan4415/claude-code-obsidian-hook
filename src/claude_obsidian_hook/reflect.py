"""セッションの振り返りを生成してObsidianに保存するモジュール.

save.pyからバックグラウンドプロセスとして起動され、
Claude CLIで振り返りを生成し、Obsidianのノートを更新する。

Usage:
    python -m claude_obsidian_hook.reflect \\
        <transcript_path> <session_id> <obsidian_history_path>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from claude_obsidian_hook.transcript import (
    extract_messages,
    extract_metadata,
    format_as_markdown,
    parse_transcript,
)

CLAUDE_CLI = "/usr/local/bin/claude"
OBSIDIAN_CLI = "/usr/local/bin/obsidian"
REFLECTIONS_PATH = "coding/reflections.md"
LOG_DIR = Path.home() / ".claude" / "logs"
LOG_FILE = LOG_DIR / "obsidian-hook.log"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """ログ設定を初期化する."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _obsidian_command(action: str, **kwargs: str) -> subprocess.CompletedProcess[str]:
    """obsidian CLIコマンドを実行する.

    Args:
        action: 実行するアクション（read, append, create等）.
        **kwargs: コマンドに渡すキーワード引数.

    Returns:
        CompletedProcessオブジェクト.
    """
    cmd = [OBSIDIAN_CLI, action]
    for key, value in kwargs.items():
        cmd.append(f"{key}={value}")
    logger.info("obsidian command: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _build_prompt(transcript_text: str) -> str:
    """振り返り生成用のプロンプトを構築する.

    Args:
        transcript_text: Markdown形式のセッション内容.

    Returns:
        プロンプト文字列.
    """
    return f"""以下のClaude Codeセッションのやり取りを分析し、\
振り返りを生成してください。

## 出力形式（箇条書きで簡潔に）
- セッション概要: 何をしたか1-2文で
- 良かった点: 効率的だった点、うまくいった点
- 反省点: 改善すべき点、非効率だった点
- 次回への教訓: 具体的で実行可能なアクション

## セッション内容
{transcript_text}"""


def generate_reflection(transcript_text: str) -> str:
    """Claude CLIで振り返りを生成する.

    Args:
        transcript_text: Markdown形式のセッション内容.

    Returns:
        生成された振り返りテキスト.
    """
    prompt = _build_prompt(transcript_text)
    result = subprocess.run(
        [CLAUDE_CLI, "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        msg = f"claude CLI failed: {result.stderr}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def _extract_summary_from_reflection(reflection: str) -> str:
    """振り返りテキストからセッション概要行を抽出する.

    Args:
        reflection: 振り返りテキスト.

    Returns:
        概要文字列。見つからない場合は"セッション振り返り".
    """
    for line in reflection.splitlines():
        if "セッション概要" in line:
            # "- セッション概要: ..." の形式から概要部分を抽出
            parts = line.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip()
    return "セッション振り返り"


def append_reflection_to_history(obsidian_history_path: str, reflection: str) -> None:
    """Obsidianのhistoryノートに振り返りを追記する.

    Args:
        obsidian_history_path: Obsidian上のhistoryノートパス.
        reflection: 振り返りテキスト.
    """
    content = f"\\n## 振り返り\\n{reflection}"
    result = _obsidian_command("append", path=obsidian_history_path, content=content)
    if result.returncode != 0:
        logger.error("historyノートへの追記に失敗: %s", result.stderr)
    else:
        logger.info("historyノートに振り返りを追記しました: %s", obsidian_history_path)


def _ensure_reflections_note() -> None:
    """coding/reflections.mdが存在しなければ作成する."""
    result = _obsidian_command("read", path=REFLECTIONS_PATH)
    if result.returncode != 0:
        logger.info("reflections.mdが見つかりません。新規作成します。")
        create_result = _obsidian_command(
            "create",
            path=REFLECTIONS_PATH,
            content="# 振り返りログ\\n\\nセッションごとの教訓を蓄積する。\\n",
        )
        if create_result.returncode != 0:
            logger.error("reflections.mdの作成に失敗: %s", create_result.stderr)


def append_lesson_to_reflections(date: str, summary: str, lesson: str) -> None:
    """教訓をcoding/reflections.mdに追記する.

    Args:
        date: 日付文字列.
        summary: セッション概要.
        lesson: 教訓テキスト.
    """
    _ensure_reflections_note()
    content = f"\\n### {date} - {summary}\\n{lesson}"
    result = _obsidian_command("append", path=REFLECTIONS_PATH, content=content)
    if result.returncode != 0:
        logger.error("reflections.mdへの追記に失敗: %s", result.stderr)
    else:
        logger.info("reflections.mdに教訓を追記しました")


def _extract_lesson_from_reflection(reflection: str) -> str:
    """振り返りテキストから教訓部分を抽出する.

    Args:
        reflection: 振り返りテキスト.

    Returns:
        教訓テキスト。見つからない場合は振り返り全体.
    """
    lines = reflection.splitlines()
    lesson_lines: list[str] = []
    capturing = False
    for line in lines:
        if "次回への教訓" in line:
            capturing = True
            lesson_lines.append(line)
            continue
        if capturing:
            # 次のセクションが始まったら停止
            if line.startswith("- ") and ":" in line and "教訓" not in line:
                break
            lesson_lines.append(line)
    if lesson_lines:
        return "\n".join(lesson_lines)
    return reflection


def run_reflection(
    transcript_path: str,
    session_id: str,
    obsidian_history_path: str,
) -> None:
    """振り返り処理のメインフロー.

    Args:
        transcript_path: JONLファイルのパス.
        session_id: セッションID.
        obsidian_history_path: Obsidian上のhistoryノートパス.
    """
    logger.info(
        "振り返り処理を開始: session_id=%s, transcript=%s",
        session_id,
        transcript_path,
    )

    # 1. transcriptを解析
    records = parse_transcript(transcript_path)
    if not records:
        logger.warning("transcriptが空です。振り返りをスキップします。")
        return

    messages = extract_messages(records)
    metadata = extract_metadata(records)

    if not messages:
        logger.warning("メッセージが見つかりません。振り返りをスキップします。")
        return

    transcript_text = format_as_markdown(messages, metadata)

    # 2. Claude CLIで振り返り生成
    reflection = generate_reflection(transcript_text)
    logger.info("振り返りを生成しました（%d文字）", len(reflection))

    # 3. historyノートに追記
    append_reflection_to_history(obsidian_history_path, reflection)

    # 4. 教訓をreflections.mdに蓄積
    date = (metadata.start_time or "unknown")[:10]
    summary = _extract_summary_from_reflection(reflection)
    lesson = _extract_lesson_from_reflection(reflection)
    append_lesson_to_reflections(date, summary, lesson)

    logger.info("振り返り処理が完了しました: session_id=%s", session_id)


def main() -> None:
    """コマンドラインエントリポイント."""
    parser = argparse.ArgumentParser(
        description="Claude Codeセッションの振り返りを生成してObsidianに保存する"
    )
    parser.add_argument("transcript_path", help="JONLファイルのパス")
    parser.add_argument("session_id", help="セッションID")
    parser.add_argument(
        "obsidian_history_path",
        help="保存済みhistoryノートのObsidianパス",
    )
    args = parser.parse_args()

    _setup_logging()

    try:
        run_reflection(
            transcript_path=args.transcript_path,
            session_id=args.session_id,
            obsidian_history_path=args.obsidian_history_path,
        )
    except Exception:
        logger.exception("振り返り処理中にエラーが発生しました")
        sys.exit(1)


if __name__ == "__main__":
    main()
