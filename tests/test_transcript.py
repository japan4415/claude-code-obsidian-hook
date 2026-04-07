"""transcript.pyのテスト."""

from __future__ import annotations

import json

import pytest

from claude_obsidian_hook.transcript import (
    Message,
    SessionMetadata,
    extract_messages,
    extract_metadata,
    format_as_markdown,
    parse_transcript,
)


@pytest.fixture
def sample_jsonl(tmp_path):
    """テスト用のJSONLファイルを作成する."""
    data = [
        {
            "type": "user",
            "uuid": "1",
            "timestamp": "2026-04-07T10:00:00Z",
            "sessionId": "sess1",
            "cwd": "/project",
            "message": {"role": "user", "content": "Hello"},
        },
        {
            "type": "assistant",
            "uuid": "2",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "Hi there!"},
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
        {
            "type": "tool_result",
            "toolUseResult": {
                "tool_use_id": "t1",
                "content": "result",
                "is_error": False,
            },
        },
    ]
    path = tmp_path / "test.jsonl"
    path.write_text("\n".join(json.dumps(d) for d in data))
    return path


class TestParseTranscript:
    def test_parse_transcript_valid(self, sample_jsonl):
        records = parse_transcript(sample_jsonl)
        assert len(records) == 3
        assert records[0]["type"] == "user"
        assert records[1]["type"] == "assistant"
        assert records[2]["type"] == "tool_result"

    def test_parse_transcript_broken_lines(self, tmp_path):
        path = tmp_path / "broken.jsonl"
        path.write_text(
            '{"type": "user", "message": {"role": "user", "content": "ok"}}\n'
            "not valid json\n"
            '{"type": "assistant", "message": {"role": "assistant", "content": []}}\n'
        )
        records = parse_transcript(path)
        assert len(records) == 2

    def test_parse_transcript_empty_lines(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text('{"type": "user"}\n\n{"type": "assistant"}\n')
        records = parse_transcript(path)
        assert len(records) == 2


class TestExtractMessages:
    def test_extract_messages_user(self, sample_jsonl):
        records = parse_transcript(sample_jsonl)
        messages = extract_messages(records)
        user_msgs = [m for m in messages if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Hello"
        assert user_msgs[0].timestamp == "2026-04-07T10:00:00Z"
        assert user_msgs[0].model is None

    def test_extract_messages_assistant(self, sample_jsonl):
        records = parse_transcript(sample_jsonl)
        messages = extract_messages(records)
        asst_msgs = [m for m in messages if m.role == "assistant"]
        assert len(asst_msgs) == 1
        assert asst_msgs[0].content == "Hi there!"
        assert asst_msgs[0].model == "claude-sonnet-4-6"

    def test_extract_messages_mixed_content(self, tmp_path):
        data = [
            {
                "type": "user",
                "message": {"role": "user", "content": "plain string"},
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "part1"},
                        {"type": "text", "text": "part2"},
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "ignore me"},
                        {"type": "text", "text": "response1"},
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Bash",
                            "input": {},
                        },
                        {"type": "text", "text": "response2"},
                    ],
                },
            },
        ]
        path = tmp_path / "mixed.jsonl"
        path.write_text("\n".join(json.dumps(d) for d in data))
        records = parse_transcript(path)
        messages = extract_messages(records)

        assert len(messages) == 3
        assert messages[0].content == "plain string"
        assert messages[1].content == "part1\npart2"
        assert messages[2].content == "response1\nresponse2"

    def test_extract_messages_skips_tool_result(self, sample_jsonl):
        records = parse_transcript(sample_jsonl)
        messages = extract_messages(records)
        assert all(m.role in ("user", "assistant") for m in messages)
        assert len(messages) == 2


class TestExtractMetadata:
    def test_extract_metadata(self, sample_jsonl):
        records = parse_transcript(sample_jsonl)
        metadata = extract_metadata(records)
        assert metadata.session_id == "sess1"
        assert metadata.cwd == "/project"
        assert metadata.start_time == "2026-04-07T10:00:00Z"
        assert metadata.model == "claude-sonnet-4-6"
        assert metadata.total_input_tokens == 100
        assert metadata.total_output_tokens == 50

    def test_extract_metadata_multiple_usage(self, tmp_path):
        data = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 200, "output_tokens": 100},
                },
            },
        ]
        path = tmp_path / "multi.jsonl"
        path.write_text("\n".join(json.dumps(d) for d in data))
        records = parse_transcript(path)
        metadata = extract_metadata(records)
        assert metadata.total_input_tokens == 300
        assert metadata.total_output_tokens == 150

    def test_extract_metadata_empty(self):
        metadata = extract_metadata([])
        assert metadata.session_id is None
        assert metadata.total_input_tokens == 0


class TestFormatAsMarkdown:
    def test_format_as_markdown(self):
        messages = [
            Message(role="user", content="質問です"),
            Message(role="assistant", content="回答です"),
        ]
        metadata = SessionMetadata(
            session_id="sess1",
            cwd="/project",
            start_time="2026-04-07T10:00:00.000Z",
            model="claude-sonnet-4-6",
            total_input_tokens=100,
            total_output_tokens=50,
        )
        result = format_as_markdown(messages, metadata)

        assert "## セッション情報" in result
        assert "- 日時: 2026-04-07 10:00:00" in result
        assert "- プロジェクト: /project" in result
        assert "- モデル: claude-sonnet-4-6" in result
        assert "- トークン: 入力 100 / 出力 50" in result
        assert "## やり取り" in result
        assert "### User" in result
        assert "質問です" in result
        assert "### Assistant" in result
        assert "回答です" in result

    def test_format_as_markdown_minimal(self):
        messages = []
        metadata = SessionMetadata()
        result = format_as_markdown(messages, metadata)

        assert "## セッション情報" in result
        assert "- トークン: 入力 0 / 出力 0" in result
        assert "日時" not in result
        assert "プロジェクト" not in result
