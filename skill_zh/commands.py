"""
两个会改文件的操作：翻译待翻译的简介，以及把简介改回英文原文。
查看状态直接用 catalog.discover。命令行和钩子都是这两个函数的薄封装。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, NamedTuple

from skill_zh import translator
from skill_zh.catalog import MAX_DESCRIPTION_LENGTH, Skill, Status, discover, is_legacy, legacy_english
from skill_zh.config import Options
from skill_zh.frontmatter import get_description, set_description
from skill_zh.state import debug_log, exclusive_lock, load_backup, save_backup


class Translated(NamedTuple):
    name: str
    translation: str


class Failed(NamedTuple):
    name: str
    reason: str


class Source(NamedTuple):
    """翻译的来源：未改动的文件全文，和要翻译的英文简介。"""

    text: str
    english: str


@dataclass
class TranslateReport:
    translated: list = field(default_factory=list)  # list[Translated]
    failed: list = field(default_factory=list)  # list[Failed]
    busy: bool = False  # 别的进程正持有锁，这次什么都没做


@dataclass
class RestoreReport:
    restored: list = field(default_factory=list)  # list[str]
    failed: list = field(default_factory=list)  # list[Failed]


def has_pending(exclude: frozenset = frozenset()) -> bool:
    return any(s.status is Status.PENDING for s in discover(exclude))


def translate_pending(options: Options, translate: Callable = translator.translate) -> TranslateReport:
    """把所有待翻译的简介翻一遍。

    每个文件先备份原件、改写通过自检才写回。失败的保持待翻译状态，下次再试。
    """
    report = TranslateReport()
    with exclusive_lock() as acquired:
        if not acquired:
            report.busy = True
            return report
        pending = [s for s in discover(options.exclude) if s.status is Status.PENDING]
        if not pending:
            return report
        sources = [_source(s) for s in pending]
        # 发给模型的键只是序号，skill 名和路径都不出去
        translations = translate({str(i): src.english for i, src in enumerate(sources)}, options.model)
        for i, (skill, source) in enumerate(zip(pending, sources)):
            translation = translations.get(str(i))
            reason = _apply(skill, source, translation)
            if reason:
                report.failed.append(Failed(skill.name, reason))
                debug_log(f"{skill.name}：{reason}")
            else:
                report.translated.append(Translated(skill.name, translation))
                debug_log(f"{skill.name}：{translation}")
    debug_log(f"本次汉化 {len(report.translated)} / {len(pending)} 个")
    return report


def _source(skill: Skill) -> Source:
    """这个 skill 翻译前的样子。

    通常就是文件现在的内容。0.1/0.2 写的双语简介已经经过我们一次了，
    它的原件要从当时的备份里拿；备份没了就退而用简介里英文那一半。
    """
    if not is_legacy(skill.description):
        return Source(skill.text, skill.description)
    backup = load_backup(skill.path)
    english = get_description(backup) if backup else None
    if english and not is_legacy(english):
        return Source(backup, english)
    english = legacy_english(skill.description)
    return Source(set_description(skill.text, english) or skill.text, english)


def _apply(skill: Skill, source: Source, translation: str | None) -> str | None:
    """把译文写进文件。成功返回 None，否则返回失败原因。"""
    if not translation:
        return "没拿到译文，下次再试"
    if len(translation) > MAX_DESCRIPTION_LENGTH:
        return f"译文超过 {MAX_DESCRIPTION_LENGTH} 个字符，保持原样"
    # 翻译要跑一两分钟，期间文件可能被 `npx skills update` 改过。
    # 写回前重读一遍，和当初读到的不一样就放弃，下次会按新内容重翻。
    try:
        with open(skill.path, encoding="utf-8") as f:
            current = f.read()
    except OSError as e:
        return f"读文件失败：{e}"
    if current != skill.text:
        return "翻译期间文件被改过，下次再试"
    text = set_description(current, translation)
    if text is None:
        return "改写后校验没通过，保持原样"
    try:
        save_backup(skill.path, source.text, translation)
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        return f"写文件失败：{e}"
    return None


def restore() -> RestoreReport:
    """把我们翻译过的 skill 的简介改回英文原文。

    不套 exclude：排除只是「不翻译」，改回英文时所有翻过的都要管。
    只改简介，之后对文件其他部分的修改保留。手动改过的简介和记录对不上，不动。
    """
    report = RestoreReport()
    for skill in discover():
        if skill.status is not Status.TRANSLATED and not is_legacy(skill.description):
            continue
        backup = load_backup(skill.path)
        original = get_description(backup) if backup else None
        if not original or is_legacy(original):
            continue
        text = set_description(skill.text, original)
        if text is None:
            report.failed.append(Failed(skill.name, "改写后校验没通过，保持原样"))
            continue
        try:
            with open(skill.path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            report.failed.append(Failed(skill.name, f"写文件失败：{e}"))
            continue
        report.restored.append(skill.name)
    return report
