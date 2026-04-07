"""reflect.pyのテスト."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from claude_obsidian_hook.reflect import (
    _extract_lesson_from_reflection,
    _extract_summary_from_reflection,
    append_lesson_to_reflections,
    append_reflection_to_history,
    generate_reflection,
    run_reflection,
)


class TestGenerateReflection:
    def test_generate_reflection(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "振り返り結果テキスト\n"

        with patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = generate_reflection("テスト用transcript")

        assert result == "振り返り結果テキスト"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/local/bin/claude"
        assert "-p" in cmd
        assert "--model" in cmd
        assert "claude-haiku-4-5-20251001" in cmd

    def test_api_failure_handling(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "CLI error"

        with patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            with pytest.raises(RuntimeError, match="claude CLI failed"):
                generate_reflection("test")

    def test_timeout_handling(self):
        import subprocess

        with patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
            with pytest.raises(subprocess.TimeoutExpired):
                generate_reflection("test")


class TestAppendReflectionToHistory:
    def test_save_reflection_to_obsidian(self):
        with patch("claude_obsidian_hook.reflect._obsidian_command") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0)
            append_reflection_to_history("coding/history/test.md", "振り返りテキスト")

        mock_cmd.assert_called_once_with(
            "append",
            path="coding/history/test.md",
            content="\\n## 振り返り\\n振り返りテキスト",
        )


class TestAppendLessonToReflections:
    def test_update_reflections_file_create(self):
        with patch("claude_obsidian_hook.reflect._obsidian_command") as mock_cmd:
            # read fails (not found) -> create -> append
            mock_cmd.side_effect = [
                MagicMock(returncode=1),  # read: not found
                MagicMock(returncode=0),  # create
                MagicMock(returncode=0),  # append
            ]
            append_lesson_to_reflections("2026-04-07", "概要", "教訓")

        assert mock_cmd.call_count == 3
        assert mock_cmd.call_args_list[0][0][0] == "read"
        assert mock_cmd.call_args_list[1][0][0] == "create"
        assert mock_cmd.call_args_list[2][0][0] == "append"

    def test_update_reflections_file_append(self):
        with patch("claude_obsidian_hook.reflect._obsidian_command") as mock_cmd:
            # read succeeds (exists) -> append
            mock_cmd.side_effect = [
                MagicMock(returncode=0),  # read: found
                MagicMock(returncode=0),  # append
            ]
            append_lesson_to_reflections("2026-04-07", "概要", "教訓")

        assert mock_cmd.call_count == 2
        assert mock_cmd.call_args_list[0][0][0] == "read"
        assert mock_cmd.call_args_list[1][0][0] == "append"


class TestExtractHelpers:
    def test_extract_summary(self):
        reflection = "- セッション概要: バグを修正した\n- 良かった点: 効率的\n"
        assert _extract_summary_from_reflection(reflection) == "バグを修正した"

    def test_extract_summary_not_found(self):
        assert _extract_summary_from_reflection("何もない") == "セッション振り返り"

    def test_extract_lesson(self):
        reflection = (
            "- セッション概要: テスト\n"
            "- 良かった点: よかった\n"
            "- 反省点: 反省\n"
            "- 次回への教訓: テストを先に書く\n"
            "  - 具体的にはTDDを実践\n"
        )
        result = _extract_lesson_from_reflection(reflection)
        assert "次回への教訓" in result
        assert "テストを先に書く" in result
        assert "具体的にはTDDを実践" in result

    def test_extract_lesson_not_found(self):
        text = "何もない振り返り"
        assert _extract_lesson_from_reflection(text) == text


class TestRunReflection:
    def test_main_flow(self, tmp_path):
        jsonl_data = [
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
                    "content": [{"type": "text", "text": "Hi!"}],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ]
        transcript = tmp_path / "test.jsonl"
        transcript.write_text("\n".join(json.dumps(d) for d in jsonl_data))

        reflection_text = "- セッション概要: テスト\n- 次回への教訓: もっとテストを書く"
        mock_claude_result = MagicMock()
        mock_claude_result.returncode = 0
        mock_claude_result.stdout = reflection_text

        with (
            patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run,
            patch("claude_obsidian_hook.reflect._obsidian_command") as mock_cmd,
        ):
            mock_run.return_value = mock_claude_result
            mock_cmd.return_value = MagicMock(returncode=0)

            run_reflection(str(transcript), "sess1", "coding/history/test.md")

        mock_run.assert_called_once()
        # append to history + read reflections + append to reflections = 3
        assert mock_cmd.call_count == 3

    def test_empty_transcript(self, tmp_path):
        transcript = tmp_path / "empty.jsonl"
        transcript.write_text("")

        with patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run:
            run_reflection(str(transcript), "sess1", "coding/history/test.md")
            mock_run.assert_not_called()

    def test_no_messages(self, tmp_path):
        data = [
            {
                "type": "tool_result",
                "toolUseResult": {
                    "tool_use_id": "t1",
                    "content": "r",
                    "is_error": False,
                },
            },
        ]
        transcript = tmp_path / "no_msg.jsonl"
        transcript.write_text(json.dumps(data[0]))

        with patch("claude_obsidian_hook.reflect.subprocess.run") as mock_run:
            run_reflection(str(transcript), "sess1", "coding/history/test.md")
            mock_run.assert_not_called()
