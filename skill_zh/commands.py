"""
The three operations skill-zh offers: list status, translate what is pending,
and restore the original English. The CLI and the hook are thin wrappers
around these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from skill_zh import translator
from skill_zh.catalog import LEGACY_SEPARATOR, MAX_DESCRIPTION_LENGTH, Skill, Status, discover, is_legacy
from skill_zh.config import Options
from skill_zh.frontmatter import get_description, set_description
from skill_zh.state import debug_log, exclusive_lock, load_backup, save_backup


@dataclass
class TranslateReport:
    translated: list[tuple[str, str]] = field(default_factory=list)  # (name, translation)
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
    original is recorded first. A failed skill stays pending and is retried
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
        by_key = {f"{i}:{s.name}": (s, *_original(s)) for i, s in enumerate(pending)}
        translations = translate({key: english for key, (_, _, english) in by_key.items()}, options.model)
        for key, (skill, original_text, _) in by_key.items():
            translation = translations.get(key)
            reason = _apply(skill, original_text, translation)
            if reason:
                report.failed.append((skill.name, reason))
                debug_log(f"{skill.name}：{reason}")
            else:
                report.translated.append((skill.name, translation))
                debug_log(f"{skill.name}：{translation}")
    debug_log(f"本次汉化 {len(report.translated)} / {len(pending)} 个")
    return report


def _original(skill: Skill) -> tuple[str, str]:
    """The untouched file text and English description to translate from.

    Usually that is the file as it is now. A 0.1/0.2 bilingual description
    already went through us once, so its original is the earlier backup, or
    failing that, the English half of the description.
    """
    if not is_legacy(skill.description):
        return skill.text, skill.description
    backup = load_backup(skill.path)
    english = get_description(backup) if backup else None
    if english and not is_legacy(english):
        return backup, english
    english = skill.description.split(LEGACY_SEPARATOR, 1)[1]
    return set_description(skill.text, english) or skill.text, english


def _apply(skill: Skill, original_text: str, translation: str | None) -> str | None:
    """Write the translation; return why it couldn't be, or None on success."""
    if not translation:
        return "没拿到译文，下次再试"
    if len(translation) > MAX_DESCRIPTION_LENGTH:
        return f"译文超过 {MAX_DESCRIPTION_LENGTH} 个字符，保持原样"
    text = set_description(skill.text, translation)
    if text is None:
        return "改写后校验没通过，保持原样"
    try:
        save_backup(skill.path, original_text, translation)
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        return f"写文件失败：{e}"
    return None


def restore(options: Options) -> list[str]:
    """Put the original description back into every skill we translated.

    Only the description is restored, so edits to the rest of the file since
    then are kept. A description edited by hand no longer matches our record
    and is left alone.
    """
    restored = []
    for skill in discover(options):
        if skill.status is not Status.TRANSLATED and not is_legacy(skill.description):
            continue
        backup = load_backup(skill.path)
        original = get_description(backup) if backup else None
        if not original or is_legacy(original):
            continue
        text = set_description(skill.text, original)
        if text is None:
            continue
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(text)
        restored.append(skill.name)
    return restored
