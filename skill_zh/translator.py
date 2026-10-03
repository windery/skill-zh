"""
Translate descriptions by calling ``claude -p`` with the user's own login.

The child session loads no settings sources and gets no tools, so it has no
plugins and no hooks: it can't fire this plugin's hooks and recurse. The
``SKILL_ZH_CHILD`` variable is a second guard for setups where settings still
load.

Descriptions go out as JSON, but translations come back as plain text blocks
under ``@@@ <key>`` marker lines. JSON is a poor reply format here: complete
translations keep quoted trigger phrases such as ``"debug this"``, and models
routinely leave those quotes unescaped, which breaks the whole reply.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from skill_zh.catalog import has_chinese
from skill_zh.state import debug_log, state_dir

# Full translations run several times longer than the old summaries; smaller
# batches keep each reply short enough for the model to finish reliably.
BATCH_SIZE = 10
TIMEOUT_SECONDS = 300
CHILD_ENV = "SKILL_ZH_CHILD"

PROMPT = """你是技术翻译。下面 JSON 的每个值是一个 AI 编程助手 skill 的英文简介（description）。
这段简介既显示在菜单里给人看，也是 AI 判断「什么时候该用这个 skill」的依据，
而且翻译后不再保留英文原文。所以要完整翻译，不能概括或删减。
- 意思完整保留，尤其是「什么时候用」「什么时候不用」的条件
- 引号里的用户原话和触发词保留原文，例如 "diagnose"、"debug this"
- skill 名、命令、产品名、文件名保留原文，例如 /triage、CLAUDE.md、GitHub
- 中文和英文之间加一个空格；不要在整段译文外面再加引号

按下面的格式输出，每条一段，标记行里的键与输入完全相同，不要输出任何其他内容：

@@@ <键>
<中文译文>

输入：
{payload}"""

_MARKER = re.compile(r"^@@@\s*(\S+)\s*$", re.M)


def translate(descriptions: dict[str, str], model: str) -> dict[str, str]:
    """Map each key to a complete Chinese translation of its English description.

    Keys whose translation failed are missing from the result; callers retry
    them on the next run.
    """
    keys = list(descriptions)
    result = {}
    for i in range(0, len(keys), BATCH_SIZE):
        batch = {k: descriptions[k] for k in keys[i : i + BATCH_SIZE]}
        prompt = PROMPT.format(payload=json.dumps(batch, ensure_ascii=False, indent=1))
        try:
            reply = _call_claude(prompt, model)
        except (OSError, subprocess.SubprocessError) as e:
            debug_log(f"翻译调用失败：{e!r}")
            continue
        result.update(parse_reply(reply, batch))
    return result


def parse_reply(reply: str, batch: dict[str, str]) -> dict[str, str]:
    """Split the reply at its ``@@@ <key>`` markers and keep only usable translations.

    Text before the first marker, unknown keys, code fences and translations
    without any Chinese are dropped; whitespace inside a translation collapses
    to single spaces, since a description is one line.
    """
    markers = list(_MARKER.finditer(reply))
    result = {}
    for marker, following in zip(markers, [*markers[1:], None]):
        key = marker.group(1)
        block = reply[marker.end() : following.start() if following else len(reply)]
        text = " ".join(word for word in block.split() if not word.startswith("```"))
        if key in batch and has_chinese(text):
            result[key] = text
    if not result:
        debug_log(f"没能从回复里解析出译文：{reply[:200]!r}")
    return result


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
