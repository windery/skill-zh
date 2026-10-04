"""
找出已安装的 skill，判断每个简介处于什么状态。

译文是英文原文的完整翻译，引号里的触发词、命令和名字保持原样。必须完整而不是概括，
因为简介也是模型判断「什么时候用这个 skill」的依据，而且翻译后不再保留英文。

「是不是我们翻的」不看文件里有没有什么标记，看状态目录里的记录：文件里的简介和当初
写进去的译文一字不差才算已汉化。作者更新 skill 后（又变回英文）会重新翻译；用户手动
改过的中文算用户自己的，不会被当成我们的译文。
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from enum import Enum

from skill_zh.config import skill_roots
from skill_zh.frontmatter import get_description
from skill_zh.state import load_translation
from skill_zh.text import is_mostly_chinese

# 0.1 和 0.2 版写的是「一句话概括 ｜ EN: 英文原文」，这种简介要按原文重新完整翻译
LEGACY_SEPARATOR = " ｜ EN: "
# Codex 和 Agent Skills 规范都限制 description 不超过 1024 个字符，超了整个 skill 加载不了
MAX_DESCRIPTION_LENGTH = 1024
# 根目录下这些子目录不是 skill：claude.ai 同步下来的、Codex 自带的
IGNORED_DIRS = frozenset({"synced", ".system"})


class Status(str, Enum):
    PENDING = "待翻译"
    TRANSLATED = "已汉化"
    ALREADY_CHINESE = "本来就是中文"
    NO_DESCRIPTION = "无简介"


@dataclass
class Skill:
    name: str
    path: str  # 真实路径（软链接已解析）
    text: str
    description: str | None
    status: Status


def classify(description: str | None, our_translation: str | None) -> Status:
    if not description:
        return Status.NO_DESCRIPTION
    if description == our_translation:
        return Status.TRANSLATED
    if is_legacy(description):
        return Status.PENDING
    if is_mostly_chinese(description):
        return Status.ALREADY_CHINESE
    return Status.PENDING


def is_legacy(description: str | None) -> bool:
    return bool(description) and LEGACY_SEPARATOR in description


def legacy_english(description: str) -> str:
    """旧版双语简介里的英文那一半。"""
    return description.split(LEGACY_SEPARATOR, 1)[1]


def discover(exclude: frozenset = frozenset()) -> list:
    """列出所有要管的 skill，每个只出现一次。

    几个根目录经常互相软链接（~/.claude/skills/x -> ~/.agents/skills/x），
    所以按真实路径去重，读写也都走真实路径。只扫根目录的直接子目录。
    """
    skills, seen = [], set()
    for root in skill_roots():
        for path in sorted(glob.glob(os.path.join(root, "*", "SKILL.md"))):
            name = os.path.basename(os.path.dirname(path))
            real = os.path.realpath(path)
            if name in IGNORED_DIRS or name in exclude or real in seen:
                continue
            seen.add(real)
            try:
                with open(real, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            description = get_description(text)
            status = classify(description, load_translation(real))
            skills.append(Skill(name=name, path=real, text=text, description=description, status=status))
    return skills
