"""
Hook handler for SessionStart and PostToolUse(Bash).

Both hooks are declared ``async`` in hooks/hooks.json so even the scan never
holds up the session. The translation itself runs in a detached process:
Claude Code cancels async hooks that are still running when the session
ends (``--debug`` logs ``Hook SessionStart:startup ... cancelled``), and a
``claude -p`` session ends long before a translation batch comes back.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import TextIO

from skill_zh import commands
from skill_zh.config import load_options
from skill_zh.state import state_dir
from skill_zh.translator import CHILD_ENV

# Commands that look like installing or updating skills: the `skills` CLI, or
# anything that writes into a skills directory (cp, git clone, ...). False
# positives only cost a cheap scan that finds nothing to do.
INSTALL_COMMAND = re.compile(r"\bskills?\b.*\b(add|install|update|upgrade)\b|/skills(/|\b)", re.I)

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def should_run(payload: dict) -> bool:
    if payload.get("hook_event_name") == "PostToolUse":
        command = (payload.get("tool_input") or {}).get("command") or ""
        return bool(INSTALL_COMMAND.search(command))
    return True


def main(stdin: TextIO) -> None:
    if os.environ.get(CHILD_ENV):
        return  # We are inside our own translation call.
    try:
        payload = json.load(stdin)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict) or not should_run(payload):
        return
    if commands.has_pending(load_options()):
        spawn_translation()


def spawn_translation() -> None:
    """Start ``python3 <plugin>/skill_zh translate`` in its own process session.

    A new session puts it outside the hook's process group, so cancelling the
    hook doesn't take the translation down with it. It inherits the hook's
    environment, including the ``CLAUDE_PLUGIN_OPTION_*`` values.
    """
    os.makedirs(state_dir(), mode=0o700, exist_ok=True)
    subprocess.Popen(
        [sys.executable, os.path.join(PLUGIN_ROOT, "skill_zh"), "translate"],
        cwd=state_dir(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
