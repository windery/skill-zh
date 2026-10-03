"""Command line interface: ``python3 -m skill_zh {status,translate,restore}``."""

from __future__ import annotations

import argparse
import os

from skill_zh import __version__, commands
from skill_zh.catalog import Status
from skill_zh.config import load_options
from skill_zh.state import log_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-zh",
        description="给英文 skill 简介补上中文说明（英文原文保留，触发词不变）。",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", metavar="{status,translate,restore}")
    sub.add_parser("status", help="列出每个 skill 的汉化状态（默认）")
    # `run` was the 0.1.0 name of `translate`; keep it working.
    sub.add_parser("translate", aliases=["run"], help="立刻翻译所有待翻译的 skill")
    sub.add_parser("restore", help="把改过的简介全部改回英文原文")
    args = parser.parse_args(argv)

    options = load_options()
    if args.command in ("translate", "run"):
        return _translate(options)
    if args.command == "restore":
        return _restore(options)
    return _status(options)


def _status(options) -> int:
    skills = commands.status(options)
    if not skills:
        print("没找到任何 skill")
        return 0
    home = os.path.expanduser("~")
    width = max(len(s.name) for s in skills)
    for s in sorted(skills, key=lambda s: (list(Status).index(s.status), s.name)):
        print(f"{s.name:<{width}}  {s.status.value:<6}  {s.path.replace(home, '~', 1)}")
    # A closing tally, so whoever relays this output (often a model) doesn't have to count.
    counts = [(status, sum(s.status is status for s in skills)) for status in Status]
    tally = "，".join(f"{status.value} {n}" for status, n in counts if n or status is Status.PENDING)
    print(f"共 {len(skills)} 个：{tally}")
    return 0


def _translate(options) -> int:
    report = commands.translate_pending(options)
    if report.busy:
        # Usually the SessionStart hook got there first; that's not an error.
        print("后台已经在翻译了（多半是开会话时自动触发的），一两分钟后运行 status 查看结果")
        return 0
    if not report.translated and not report.failed:
        print("没有需要翻译的 skill")
        return 0
    for name, summary in report.translated:
        print(f"{name}：{summary}")
    for name, reason in report.failed:
        print(f"{name}：{reason}")
    print(f"本次汉化 {len(report.translated)} / {len(report.translated) + len(report.failed)} 个")
    if report.failed:
        print(f"详情见日志：{log_path()}")
    return 1 if report.failed else 0


def _restore(options) -> int:
    names = commands.restore(options)
    for name in names:
        print(f"已改回英文：{name}")
    print(f"共改回 {len(names)} 个")
    return 0
