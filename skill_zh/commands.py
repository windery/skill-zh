"""
The three operations skill-zh offers: list status, translate what is pending,
and restore the original English. The CLI and the hook are thin wrappers
around these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from skill_zh import translator
from skill_zh.catalog import SEPARATOR, Skill, Status, compose, discover
from skill_zh.config import Options
from skill_zh.frontmatter import get_description, set_description
from skill_zh.state import debug_log, exclusive_lock, load_backup, save_backup


@dataclass
class TranslateReport:
    translated: list[tuple[str, str]] = field(default_factory=list)  # (name, summary)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)
    busy: bool = False  # another process held the lock; nothing was attempted


def status(options: Options) -> list[Skill]:
    return discover(options)


def has_pending(options: Options) -> bool:
    return any(s.status is Status.PENDING for s in discover(options))


def translate_pending(
    options: Options,
    translate: Callable[[dict[str, str], str], dict[str, str]] = translator.translate,
) -> TranslateReport:
    """Translate every pending description in one batch run.

    A file is written only after its rewrite passes verification, and its
    original is backed up first. A failed skill stays pending and is retried
    on the next run.
    """
    report = TranslateReport()
    with exclusive_lock() as acquired:
        if not acquired:
            report.busy = True
            return report
        pending = [s for s in discover(options) if s.status is Status.PENDING]
        if not pending:
            return report
        # Index keys keep two same-named skills from different roots apart.
        by_key = {f"{i}:{s.name}": s for i, s in enumerate(pending)}
        summaries = translate({k: s.description for k, s in by_key.items()}, options.model)
        for key, skill in by_key.items():
            reason = _apply(skill, summaries.get(key))
            if reason:
                report.failed.append((skill.name, reason))
                debug_log(f"{skill.name}：{reason}")
            else:
                report.translated.append((skill.name, summaries[key]))
                debug_log(f"{skill.name}：{summaries[key]}")
    debug_log(f"本次汉化 {len(report.translated)} / {len(pending)} 个")
    return report


def _apply(skill: Skill, summary: str | None) -> str | None:
    """Write the translated description; return why it couldn't be, or None on success."""
    if not summary:
        return "没拿到译文，下次再试"
    description = compose(summary, skill.description)
    if description is None:
        return "原简介太长，加不下中文"
    text = set_description(skill.text, description)
    if text is None:
        return "改写后校验没通过，保持原样"
    try:
        save_backup(skill.path, skill.text)
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        return f"写文件失败：{e}"
    return None


def restore(options: Options) -> list[str]:
    """Put the original description back into every translated skill that has a backup.

    Only the description is restored. If the skill was edited or updated since,
    those changes are kept.
    """
    restored = []
    for skill in discover(options):
        if skill.status is not Status.TRANSLATED:
            continue
        backup = load_backup(skill.path)
        original = get_description(backup) if backup else None
        if not original or SEPARATOR in original:
            continue
        text = set_description(skill.text, original)
        if text is None:
            continue
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(text)
        restored.append(skill.name)
    return restored
