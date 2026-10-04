"""
调用 claude -p 翻译简介，用的是用户自己的 Claude Code 登录。

子会话不加载任何设置、不给工具，所以里面没有插件也没有钩子，不会反过来触发
本插件。SKILL_ZH_CHILD 环境变量是第二道保险，防止某些环境下设置仍被加载。

发出去的是 JSON，键只是序号，skill 名和路径都不会发给模型。回来的译文不用 JSON，
而是「@@@ 键」标记行加一段纯文本：完整翻译会保留 "debug this" 这类带引号的触发词，
模型经常不转义引号，整段 JSON 就解析不了。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from skill_zh.state import debug_log, ensure_state_dir
from skill_zh.text import is_mostly_chinese

# 完整翻译比原来的一句话概括长好几倍，每批少一点，模型才能稳定地把一整批写完
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

_MARKER = re.compile(r"^@@@[ \t]*(.+?)[ \t]*$", re.M)


def translate(descriptions: dict, model: str) -> dict:
    """把每个键对应的英文简介翻成完整的中文译文。

    翻译失败的键不出现在结果里，调用方下次再试。
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


def parse_reply(reply: str, batch: dict) -> dict:
    """按「@@@ 键」标记把回复切成段，只留下能用的译文。

    第一个标记之前的文字、不认识的键、代码围栏都丢掉。译文得是中文为主，
    模型拒答或者半中半英的不要。译文内部的换行和多余空白压成单个空格，简介就是一行。
    """
    markers = list(_MARKER.finditer(reply))
    result = {}
    for marker, following in zip(markers, [*markers[1:], None]):
        key = marker.group(1)
        block = reply[marker.end() : following.start() if following else len(reply)]
        text = " ".join(word for word in block.split() if not word.startswith("```"))
        if key in batch and is_mostly_chinese(text):
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
        raise FileNotFoundError("找不到 claude 命令")
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
        cwd=ensure_state_dir(),  # 在状态目录里跑，免得把某个项目的 CLAUDE.md 带进子会话
        env={**os.environ, CHILD_ENV: "1"},
    )
    if proc.returncode != 0:
        raise subprocess.SubprocessError(f"claude 退出码 {proc.returncode}：{proc.stderr.strip()[:200]}")
    return proc.stdout
