"""把英文 skill 简介翻译成中文，并保留原文以便随时恢复。"""

import json
import os

# 版本号只在 .claude-plugin/plugin.json 里维护一份，这里读出来给 --version 用。
_MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-plugin", "plugin.json")


def _read_version() -> str:
    try:
        with open(_MANIFEST, encoding="utf-8") as f:
            return str(json.load(f)["version"])
    except (OSError, ValueError, KeyError):
        return "unknown"


__version__ = _read_version()
