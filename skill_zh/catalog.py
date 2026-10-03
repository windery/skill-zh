"""
Find installed skills and decide what state each description is in.

A translated description is a complete Chinese translation of the original,
with quoted trigger phrases, commands and names kept verbatim. It has to be
complete rather than a summary: the description is also what the model reads
to decide when to use a skill, and nothing of the English is kept beside it.

Whether a description is our translation is decided by the record in the
state directory, not by anything in the file: it counts as translated only
while it still equals the text we wrote. A skill updated upstream (English
again) or edited by hand (some other Chinese) is never mistaken for ours.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from enum import Enum

from skill_zh.config import Options, skill_roots
from skill_zh.frontmatter import get_description
from skill_zh.state import load_translation

# 0.1 and 0.2 wrote "<one-line summary> ｜ EN: <original>". Such descriptions
# are translated again, in full, from the original.
LEGACY_SEPARATOR = " ｜ EN: "
# Codex and the Agent Skills spec cap descriptions at 1024 characters, and a
# skill over the cap fails to load at all. Never write past it.
MAX_DESCRIPTION_LENGTH = 1024

_CJK = re.compile("[一-鿿]")
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


def is_mostly_chinese(text: str) -> bool:
    """True when Chinese characters at least match English words in number.

    A plain "contains Chinese" test is wrong: many English descriptions embed a
    few Chinese trigger phrases and are still unreadable to the user.
    """
    return len(_CJK.findall(text)) >= len(_ENGLISH_WORD.findall(text))


def has_chinese(text: str) -> bool:
    return bool(_CJK.search(text))


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
            description = get_description(text)
            status = classify(description, load_translation(real))
            skills.append(Skill(name=name, path=real, text=text, description=description, status=status))
    return skills
