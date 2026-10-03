"""
Translate descriptions by calling ``claude -p`` with the user's own login.

The child session loads no settings sources and gets no tools, so it has no
plugins and no hooks: it can't fire this plugin's hooks and recurse. The
``SKILL_ZH_CHILD`` variable is a second guard for setups where settings still
load. Descriptions go out in batches and must come back as one JSON object
keyed exactly like the request; anything else in the reply is ignored.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from skill_zh.catalog import has_chinese
from skill_zh.state import debug_log, state_dir

BATCH_SIZE = 15
SUMMARY_MAX_CHARS = 80
TIMEOUT_SECONDS = 300
CHILD_ENV = "SKILL_ZH_CHILD"

PROMPT = """你是技术翻译。下面 JSON 的每个值是一个 AI 编程助手 skill 的英文简介。
把每条改写成简体中文的一句话说明（不超过 {limit} 个汉字），说清它是干什么的、什么时候用。
- skill 名、命令、产品名、文件名保留原文，中文和英文之间加一个空格
- 不加引号，不换行
- 只输出一个 JSON 对象：键与输入完全相同，值是中文说明。不要输出任何其他内容。

输入：
{payload}"""


def translate(descriptions: dict[str, str], model: str) -> dict[str, str]:
    """Map each key to a one-sentence Chinese summary of its English description.

    Keys whose translation failed are missing from the result; callers retry
    them on the next run.
    """
    keys = list(descriptions)
    result = {}
    for i in range(0, len(keys), BATCH_SIZE):
        batch = {k: descriptions[k] for k in keys[i : i + BATCH_SIZE]}
        prompt = PROMPT.format(limit=SUMMARY_MAX_CHARS, payload=json.dumps(batch, ensure_ascii=False, indent=1))
        try:
            reply = _call_claude(prompt, model)
        except (OSError, subprocess.SubprocessError) as e:
            debug_log(f"翻译调用失败：{e!r}")
            continue
        result.update(parse_reply(reply, batch))
    return result


def parse_reply(reply: str, batch: dict[str, str]) -> dict[str, str]:
    """Pull the JSON object out of the model's reply and keep only usable entries."""
    try:
        data = json.loads(reply[reply.index("{") : reply.rindex("}") + 1])
    except ValueError:
        debug_log(f"译文不是 JSON：{reply[:200]!r}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: " ".join(value.split())
        for key, value in data.items()
        if key in batch and isinstance(value, str) and has_chinese(value)
    }


def find_claude() -> str | None:
    candidates = (
        shutil.which("claude"),
        os.path.expanduser("~/.local/bin/claude"),
        os.environ.get("CLAUDE_CODE_EXECPATH"),
    )
    return next((c for c in candidates if c and os.access(c, os.X_OK)), None)


def _call_claude(prompt: str, model: str) -> str:
    exe = find_claude()
    if not exe:
        raise FileNotFoundError("claude command not found")
    os.makedirs(state_dir(), exist_ok=True)
    proc = subprocess.run(
        [
            exe,
            "-p",
            "--model",
            model,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--output-format",
            "text",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_SECONDS,
        cwd=state_dir(),  # Keep the project's CLAUDE.md out of the child's context.
        env={**os.environ, CHILD_ENV: "1"},
    )
    if proc.returncode != 0:
        raise subprocess.SubprocessError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    return proc.stdout
