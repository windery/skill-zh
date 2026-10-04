"""
SessionStart 和 PostToolUse(Bash) 两个钩子的处理逻辑。

两个钩子在 hooks/hooks.json 里都声明成 async，连扫描都不会卡住会话。
翻译本身放在一个独立进程里：会话结束时，Claude Code 会取消还在跑的后台钩子
（--debug 日志里能看到 `Hook SessionStart:startup ... cancelled`），
而一次 claude -p 会话早在翻译跑完之前就结束了。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import TextIO

from skill_zh import commands
from skill_zh.config import load_options, plugin_root
from skill_zh.state import ensure_state_dir
from skill_zh.translator import CHILD_ENV

# 看起来像在装或更新 skill 的命令：`skills` 命令行工具，或者往某个 skills 目录里写东西
# （cp、git clone 之类）。误判的代价只是多扫一遍、发现没事可做。
INSTALL_COMMAND = re.compile(r"\bskills?\b.*\b(add|install|update|upgrade)\b|/skills(/|\b)", re.I)


def should_run(payload: dict) -> bool:
    if payload.get("hook_event_name") == "PostToolUse":
        command = (payload.get("tool_input") or {}).get("command") or ""
        return bool(INSTALL_COMMAND.search(command))
    return True


def main(stdin: TextIO) -> None:
    if os.environ.get(CHILD_ENV):
        return  # 现在是在我们自己发起的翻译子会话里
    try:
        payload = json.load(stdin)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict) or not should_run(payload):
        return
    if commands.has_pending(load_options().exclude):
        spawn_translation()


def spawn_translation() -> None:
    """在独立的进程会话里启动 `python3 <插件目录>/skill_zh translate`。

    新开进程会话，它就不在钩子的进程组里，钩子被取消也带不走它。
    环境变量原样继承，包括 CLAUDE_PLUGIN_OPTION_* 里的用户配置。
    """
    subprocess.Popen(
        [sys.executable, os.path.join(plugin_root(), "skill_zh"), "translate"],
        cwd=ensure_state_dir(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
