"""共有設定定数モジュール.

複数モジュールで使用されるCLIパス等の定数を一元管理する。
"""

from __future__ import annotations

import os

OBSIDIAN_CLI = os.environ.get("OBSIDIAN_CLI", "/usr/local/bin/obsidian")
CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "/usr/local/bin/claude")
OBSIDIAN_HISTORY_PATH = os.environ.get("OBSIDIAN_HISTORY_PATH", "coding/history")
