"""save.pyのテスト."""

from __future__ import annotations

import json
import re
import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from claude_obsidian_hook.save import (
    _escape_for_obsidian,
    _generate_timestamp_filename,
    _launch_reflect,
    _read_hook_input,
    _save_to_obsidian,
    main,
)


class TestReadHookInput:
    def test_read_hook_input(self):
        data = {"session_id": "abc", "stop_hook_active": False}
        with patch("sys.stdin", StringIO(json.dumps(data))):
            result = _read_hook_input()
        assert result == data


class TestEscapeForObsidian:
    def test_escape_newlines(self):
        assert _escape_for_obsidian("a\nb") == "a\\nb"

    def test_escape_backslash(self):
        assert _escape_for_obsidian("a\\b") == "a\\\\b"

    def test_escape_backslash_then_newline(self):
        result = _escape_for_obsidian("a\\\nb")
        assert result == "a\\\\\\nb"

    def test_escape_double_quotes(self):
        assert _escape_for_obsidian('say "hello"') == 'say \\"hello\\"'

    def test_no_escape_needed(self):
        assert _escape_for_obsidian("hello") == "hello"


class TestGenerateTimestampFilename:
    def test_format(self):
        ts = _generate_timestamp_filename()
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", ts)

    def test_deterministic(self):
        from datetime import datetime, timezone

        fixed = datetime(2026, 4, 7, 10, 30, 45, tzinfo=timezone.utc)
        with patch("claude_obsidian_hook.save.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _generate_timestamp_filename()
        assert result == "2026-04-07_10-30-45"


class TestSaveToObsidian:
    def test_save_to_obsidian(self):
        with patch("claude_obsidian_hook.save.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _save_to_obsidian("coding/history/test.md", "content\nhere")

        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[0] == "/usr/local/bin/obsidian"
        assert cmd[1] == "create"


class TestLaunchReflect:
    def test_launch_reflect(self):
        with patch("claude_obsidian_hook.save.subprocess.Popen") as mock_popen:
            _launch_reflect("/path/to/transcript", "sess1", "coding/history/test.md")

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        cmd = call_kwargs[0][0]
        assert "-m" in cmd
        assert "claude_obsidian_hook.reflect" in cmd
        assert "/path/to/transcript" in cmd
        assert "sess1" in cmd
        assert call_kwargs[1]["start_new_session"] is True


    def test_passes_skip_analysis_env(self):
        with patch("claude_obsidian_hook.save.subprocess.Popen") as mock_popen:
            _launch_reflect("/path/to/transcript", "sess1", "coding/history/test.md")

        call_kwargs = mock_popen.call_args[1]
        assert "env" in call_kwargs
        assert call_kwargs["env"]["CLAUDE_SKIP_ANALYSIS"] == "1"


class TestMain:
    def test_skip_analysis_env_exits(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SKIP_ANALYSIS", "1")
        with (
            patch("claude_obsidian_hook.save._read_hook_input") as mock_read,
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0
        mock_read.assert_not_called()

    def test_missing_transcript_path_exits(self):
        data = {"stop_hook_active": False, "transcript_path": ""}
        with (
            patch("sys.stdin", StringIO(json.dumps(data))),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

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

        hook_input = {
            "stop_hook_active": False,
            "session_id": "sess1",
            "transcript_path": str(transcript),
            "cwd": "/project",
        }

        with (
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("claude_obsidian_hook.save.subprocess.run") as mock_run,
            patch("claude_obsidian_hook.save.subprocess.Popen") as mock_popen,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            main()

        assert exc_info.value.code == 0
        mock_run.assert_called_once()
        mock_popen.assert_called_once()

    def test_main_error_handling(self, tmp_path):
        jsonl_data = [
            {
                "type": "user",
                "uuid": "1",
                "timestamp": "2026-04-07T10:00:00Z",
                "sessionId": "sess1",
                "cwd": "/project",
                "message": {"role": "user", "content": "Hello"},
            },
        ]
        transcript = tmp_path / "test.jsonl"
        transcript.write_text(json.dumps(jsonl_data[0]))

        hook_input = {
            "stop_hook_active": False,
            "session_id": "sess1",
            "transcript_path": str(transcript),
        }

        with (
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch(
                "claude_obsidian_hook.save.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "obsidian"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
