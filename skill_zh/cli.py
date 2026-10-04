"""命令行：`python3 skill_zh {status,translate,restore}`。"""

from __future__ import annotations

import argparse
import os

from skill_zh import __version__, commands
from skill_zh.catalog import Status, discover
from skill_zh.config import load_options
from skill_zh.state import log_path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-zh",
        description="把英文 skill 简介完整翻译成中文（保留触发词，原文可随时恢复）。",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", metavar="{status,translate,restore}")
    sub.add_parser("status", help="列出每个 skill 的汉化状态（默认）")
    sub.add_parser("translate", help="立刻翻译所有待翻译的 skill")
    sub.add_parser("restore", help="把改过的简介全部改回英文原文")
    args = parser.parse_args(argv)

    if args.command == "translate":
        return _translate()
    if args.command == "restore":
        return _restore()
    return _status()


def _status() -> int:
    skills = discover(load_options().exclude)
    if not skills:
        print("没找到任何 skill")
        return 0
    home = os.path.expanduser("~")
    width = max(len(s.name) for s in skills)
    for s in sorted(skills, key=lambda s: (list(Status).index(s.status), s.name)):
        print(f"{s.name:<{width}}  {s.status.value:<6}  {s.path.replace(home, '~', 1)}")
    # 最后给一行汇总，转述这段输出的人（往往是模型）就不用自己数了
    counts = [(status, sum(s.status is status for s in skills)) for status in Status]
    tally = "，".join(f"{status.value} {n}" for status, n in counts if n or status is Status.PENDING)
    print(f"共 {len(skills)} 个：{tally}")
    return 0


def _translate() -> int:
    report = commands.translate_pending(load_options())
    if report.busy:
        # 多半是开会话时的钩子抢先一步了，不算错误
        print("后台已经在翻译了（多半是开会话时自动触发的），一两分钟后运行 status 查看结果")
        return 0
    if not report.translated and not report.failed:
        print("没有需要翻译的 skill")
        return 0
    for name, translation in report.translated:
        print(f"{name}：{translation}")
    for name, reason in report.failed:
        print(f"{name}：{reason}")
    print(f"本次汉化 {len(report.translated)} / {len(report.translated) + len(report.failed)} 个")
    if report.failed:
        print(f"详情见日志：{log_path()}")
    return 1 if report.failed else 0


def _restore() -> int:
    report = commands.restore()
    for name in report.restored:
        print(f"已改回英文：{name}")
    for name, reason in report.failed:
        print(f"{name}：{reason}")
    print(f"共改回 {len(report.restored)} 个")
    return 1 if report.failed else 0
