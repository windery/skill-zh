"""
Find installed skills, decide what state each description is in, and define
the bilingual description format.

A translated description reads ``<中文说明> ｜ EN: <original English>``. The
English stays because the description is also what the model reads to decide
when to use a skill; dropping the author's trigger phrases could stop the
skill from firing. Putting Chinese first means a truncated menu entry still
shows the Chinese.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from enum import Enum

from skill_zh.config import Options, skill_roots
from skill_zh.frontmatter import get_description

SEPARATOR = " ｜ EN: "
# Codex and the Agent Skills spec cap descriptions at 1024 characters, and a
# skill over the cap fails to load at all. Never write past it.
MAX_DESCRIPTION_LENGTH = 1024

_CJK = re.compile(r"[一-鿿]")
_ENGLISH_WORD = re.compile(r"[A-Za-z]+")


class Status(str, Enum):
    PENDING = "待翻译"
    TRANSLATED = "已汉化"
    ALREADY_CHINESE = "本来就是中文"
    NO_DESCRIPTION = "无简介"


@dataclass
class Skill:
    name: str
    path: str
    text: str
    description: str | None

    @property
    def status(self) -> Status:
        return classify(self.description)


def classify(description: str | None) -> Status:
    if not description:
        return Status.NO_DESCRIPTION
    if SEPARATOR in description:
        return Status.TRANSLATED
    if is_mostly_chinese(description):
        return Status.ALREADY_CHINESE
    return Status.PENDING


def is_mostly_chinese(text: str) -> bool:
    """True when Chinese characters at least match English words in number.

    A plain "contains Chinese" test is wrong: many English descriptions embed a
    few Chinese trigger phrases and are still unreadable to the user.
    """
    return len(_CJK.findall(text)) >= len(_ENGLISH_WORD.findall(text))


def has_chinese(text: str) -> bool:
    return bool(_CJK.search(text))


def compose(summary: str, original: str) -> str | None:
    """Build the bilingual description, or None if the original leaves no room.

    The summary is truncated to fit; the original is never cut, since that is
    where the trigger phrases are.
    """
    original = " ".join(original.split())
    room = MAX_DESCRIPTION_LENGTH - len(SEPARATOR) - len(original)
    if room < 10:
        return None
    if len(summary) > room:
        summary = summary[: room - 1] + "…"
    return summary + SEPARATOR + original


def discover(options: Options) -> list[Skill]:
    """Return every skill under the managed roots, each one only once.

    Roots often symlink into each other (``~/.claude/skills/x`` ->
    ``~/.agents/skills/x``), so skills are deduplicated by real path and
    always written through it.
    """
    skills, seen = [], set()
    for root in skill_roots():
        for path in sorted(glob.glob(os.path.join(root, "*", "SKILL.md"))):
            name = os.path.basename(os.path.dirname(path))
            real = os.path.realpath(path)
            if name in options.exclude or real in seen:
                continue
            seen.add(real)
            try:
                with open(real, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            skills.append(Skill(name=name, path=real, text=text, description=get_description(text)))
    return skills
