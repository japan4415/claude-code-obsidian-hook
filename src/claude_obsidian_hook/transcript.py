"""Claude Codeのセッションtranscript（JSONL形式）を解析するユーティリティモジュール."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """user/assistantメッセージを表すデータクラス.

    Attributes:
        role: "user" or "assistant".
        content: テキスト内容.
        timestamp: メッセージのタイムスタンプ（ISO 8601形式）.
        model: assistantの場合のモデル名.
    """

    role: str
    content: str
    timestamp: str | None = None
    model: str | None = None


@dataclass
class SessionMetadata:
    """セッションメタデータを表すデータクラス.

    Attributes:
        session_id: セッションID.
        cwd: 作業ディレクトリ.
        start_time: セッション開始時刻（ISO 8601形式）.
        model: 使用モデル名.
        total_input_tokens: 入力トークン合計.
        total_output_tokens: 出力トークン合計.
    """

    session_id: str | None = None
    cwd: str | None = None
    start_time: str | None = None
    model: str | None = None
    total_input_tokens: int = field(default=0)
    total_output_tokens: int = field(default=0)


def parse_transcript(path: str | Path) -> list[dict]:
    """JSONLファイルを読み込み、各行をパースして辞書のリストで返す.

    壊れた行（不正なJSON）はスキップしてログに警告を出す。

    Args:
        path: JSONLファイルのパス.

    Returns:
        パースされたレコードの辞書リスト.
    """
    path = Path(path)
    records: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(
                    "行 %d: JSONパースに失敗。スキップします。",
                    line_no,
                )
    return records


def _extract_text_from_content(content: str | list) -> str:
    """メッセージのcontentフィールドからテキストを抽出する.

    Args:
        content: 文字列またはcontent blockのリスト.

    Returns:
        抽出されたテキスト.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(texts)
    return ""


def extract_messages(records: list[dict]) -> list[Message]:
    """user/assistantメッセージのみ抽出する.

    Args:
        records: parse_transcriptで取得したレコードリスト.

    Returns:
        Messageオブジェクトのリスト.
    """
    messages: list[Message] = []
    for record in records:
        record_type = record.get("type")
        if record_type not in ("user", "assistant"):
            continue

        msg = record.get("message", {})
        role = msg.get("role", record_type)
        content = _extract_text_from_content(msg.get("content", ""))
        timestamp = record.get("timestamp")
        model = msg.get("model") if role == "assistant" else None

        messages.append(
            Message(role=role, content=content, timestamp=timestamp, model=model)
        )
    return messages


def extract_metadata(records: list[dict]) -> SessionMetadata:
    """セッションメタデータを抽出する.

    Args:
        records: parse_transcriptで取得したレコードリスト.

    Returns:
        SessionMetadataオブジェクト.
    """
    metadata = SessionMetadata()
    for record in records:
        if metadata.session_id is None and "sessionId" in record:
            metadata.session_id = record["sessionId"]
        if metadata.cwd is None and "cwd" in record:
            metadata.cwd = record["cwd"]
        if metadata.start_time is None and "timestamp" in record:
            metadata.start_time = record["timestamp"]

        msg = record.get("message", {})
        if metadata.model is None and "model" in msg:
            metadata.model = msg["model"]

        usage = msg.get("usage", {})
        metadata.total_input_tokens += usage.get("input_tokens", 0)
        metadata.total_output_tokens += usage.get("output_tokens", 0)

    return metadata


def format_as_markdown(messages: list[Message], metadata: SessionMetadata) -> str:
    """メッセージとメタデータをMarkdown形式にフォーマットする.

    Args:
        messages: Messageオブジェクトのリスト.
        metadata: SessionMetadataオブジェクト.

    Returns:
        Markdown形式の文字列.
    """
    lines: list[str] = []

    # セッション情報
    lines.append("## セッション情報")
    if metadata.start_time:
        # ISO 8601からシンプルな表示形式に変換
        display_time = metadata.start_time.replace("T", " ").split(".")[0]
        if display_time.endswith("Z"):
            display_time = display_time[:-1]
        lines.append(f"- 日時: {display_time}")
    if metadata.cwd:
        lines.append(f"- プロジェクト: {metadata.cwd}")
    if metadata.model:
        lines.append(f"- モデル: {metadata.model}")
    input_t = metadata.total_input_tokens
    output_t = metadata.total_output_tokens
    lines.append(f"- トークン: 入力 {input_t} / 出力 {output_t}")
    lines.append("")

    # やり取り
    lines.append("## やり取り")
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        lines.append(f"### {role_label}")
        lines.append(msg.content)
        lines.append("")

    return "\n".join(lines)
