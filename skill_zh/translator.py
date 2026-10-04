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

# 提示词里的术语规则来自对 30 条真实译文的核对：major 问题几乎全是术语错译和把 agent、issue 硬译成「代理」「问题」
PROMPT = """你是中文技术文档译者。下面 JSON 的每个值是一个 AI 编程助手 skill 的英文简介（description）。
这段简介既显示在菜单里给人看，也是 AI 判断「什么时候该用这个 skill」的依据，
而且翻译后不再保留英文原文。所以要完整、准确地翻译，不能概括或删减。

内容：
- 意思完整保留，尤其是「什么时候用」「什么时候不用」的条件；中心词和限定词都不能漏（changes 要译出「变更」，high-trust 要译出「高可信度」），也不要加原文没有的修饰词
- 指人的词要译出来：the user 是「用户」，you/your 是「你」，what you've already discussed 是「你们已经讨论过的内容」；it/them/their 这类指物的代词一般省略
- 引号里的用户原话和触发词是模型识别用户意图的依据，一个字母都不能改，不翻译、不改写，X 这样的占位符也照抄，引号样式也照原样：例如 "diagnose"、"debug this"、"review since X"、'grill'
- skill 名、命令、产品名、文件名保留原文，例如 /triage、CLAUDE.md、GitHub
- 作者用的强语气动词不要弱化：relentlessly 是「穷追不舍地」不是「深入」，grill 是「不留情面地追问」不是「讨论」；语气跟原文走，口语短句译成中文口语（Stop. 是「停。」，something is broken 是「某处坏了」）
- 保持原文的句子数量和层次：先说是什么，再说什么时候用，不合并也不拆分

术语：
- 开发圈通用英文词一律保留原词，不要硬译：agent、sub-agent、issue、PR、ticket、spec、bug、web、repo、commit、CI、ADR。不要写成「代理」「问题」「规格」「错误」「网络」
- git 子命令和中文社区习惯直接用英文的词也保留：merge-base、rebase、triage、dogfooding。skill 只在指 agent skill 时保留英文，指人的本领时译「技能」
- 有固定中文译名的术语用中文：integration test→集成测试，codebase→代码库，primary sources→一手来源，secrets→密钥，cutover→切换，data lineage→数据血缘，sequence diagram→时序图，deep module→深模块，domain（DDD 语境）→领域，performance regression→性能退化，glossary→术语表，第三方服务的 dashboard→控制台
- 多义词按技术语境取义：interview（agent 向用户逐条提问）→追问，brief→任务简报，router→入口，plain-language→自然语言，surface（动词）→明确列出，provisioning→搭建
- 依赖其他 skill 才懂的概念先译成中文、再括注英文，例如「深化（deepening）机会」，不要只留英文
- 同一个英文词在这一批里只用一种译法

表达：
- 先读懂整句，再按中文语序重新组织，不要逐词对译；译完通读，「规划 X 为 Y」「将 X 记录为 Y」这类中文里没人这么说的句子必须改写
- 「Use when …」译成「当用户……时使用」或「在……时使用」，不要写成「用于……时」
- 动词按中文习惯搭配：减少错误、填写表单、改写成；不用「进行」「执行」凑字；this repo 译「本仓库」，this skill 译「此 skill」
- 并列项要平行，每一项带同样的后缀（架构图、工作流图、时序图）；并列用顿号，最后一项前用「或」「和」
- 保留的英文词不带复数 -s（bugs 写 bug），skill 统一小写
- 标点用中文全角；中文和英文之间加一个空格；不要在整段译文外面再加引号

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
