"""
读写 SKILL.md 开头 YAML frontmatter 里的 description 字段。

只动这一个字段。改写是逐行替换，不把 YAML 重新序列化一遍，所以其他字段的注释、
顺序和引号写法一个字节都不变。每次改写都要通过自检才算数：新文件里的 description
必须等于要写的值，其他顶层字段必须一行不差。

有 PyYAML 就用它解析；没有的话，内置一个够用的简易解析，认得真实 skill 里出现过的
几种写法：单行、带引号、折叠块（>）、字面块（|）、多行续写。
"""

from __future__ import annotations

import json
import re

# 允许开头带 BOM；frontmatter 的换行可以是 LF 或 CRLF
_FRONTMATTER = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_DESCRIPTION_KEY = re.compile(r"description\s*:")
# 顶层字段行：行首不缩进的 `key:`
_TOP_LEVEL_KEY = re.compile(r"^[^\s#:][^:]*:")


def get_description(text: str) -> str | None:
    data = _parse(text)
    value = data.get("description") if data else None
    return value if isinstance(value, str) else None


def set_description(text: str, value: str) -> str | None:
    """返回把 description 换成 value 之后的全文；没法安全改就返回 None。

    新值写成一行双引号 JSON 字符串，它同时也是合法的 YAML 双引号标量。
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    # 跟着文件原来的换行风格走，别把 CRLF 文件改出混合换行
    newline = "\r\n" if "\r\n" in match.group(0) else "\n"
    lines = match.group(1).split(newline)
    span = _description_span(lines)
    if not span:
        return None
    start, end = span
    lines[start:end] = ["description: " + json.dumps(value, ensure_ascii=False)]
    result = text[: match.start(1)] + newline.join(lines) + text[match.end(1) :]
    return result if _verify(text, result, value) else None


def copy_description(source: str, target: str) -> str | None:
    """把 source 里的 description 连同写法原样搬进 target，其他内容不动；没法安全做就返回 None。

    restore 用它：改回英文时不只是值相同，引号、折叠块这些写法也和原件一样，
    文件其余部分没动过的话，结果和原件逐字节一致。
    """
    src, dst = _FRONTMATTER.match(source), _FRONTMATTER.match(target)
    if not src or not dst:
        return None
    src_newline = "\r\n" if "\r\n" in src.group(0) else "\n"
    dst_newline = "\r\n" if "\r\n" in dst.group(0) else "\n"
    src_lines, dst_lines = src.group(1).split(src_newline), dst.group(1).split(dst_newline)
    src_span, dst_span = _description_span(src_lines), _description_span(dst_lines)
    if not src_span or not dst_span:
        return None
    dst_lines[dst_span[0] : dst_span[1]] = src_lines[src_span[0] : src_span[1]]
    result = target[: dst.start(1)] + dst_newline.join(dst_lines) + target[dst.end(1) :]
    value = get_description(source)
    return result if value is not None and _verify(target, result, value) else None


def _verify(before: str, after: str, value: str) -> bool:
    """写回前自检：description 变成了新值，其他顶层字段一行没动；有 PyYAML 时再按解析结果比一遍。"""
    parsed = _parse(after)
    if not parsed or parsed.get("description") != value:
        return False
    if _other_top_level_lines(before) != _other_top_level_lines(after):
        return False
    try:
        import yaml  # noqa: F401
    except ImportError:
        return True  # 没有 PyYAML，只能做到文本级比对
    old, new = dict(_parse(before) or {}), dict(parsed)
    old.pop("description", None)
    new.pop("description", None)
    return old == new


def _other_top_level_lines(text: str) -> list:
    match = _FRONTMATTER.match(text)
    if not match:
        return []
    return [
        line.rstrip("\r")
        for line in match.group(1).splitlines()
        if _TOP_LEVEL_KEY.match(line) and not _DESCRIPTION_KEY.match(line)
    ]


def _parse(text: str) -> dict | None:
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    try:
        import yaml
    except ImportError:
        return {"description": _fallback_description(match.group(1))}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _description_span(lines: list) -> tuple | None:
    """description 占的行范围 [start, end)，续写行算在内。"""
    for start, line in enumerate(lines):
        if not _DESCRIPTION_KEY.match(line):
            continue
        end = start + 1
        # 续写行都有缩进；块标量中间可能夹空行
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
            end += 1
        # 末尾的空行属于下一个字段，不属于 description
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        return start, end
    return None


def _fallback_description(frontmatter: str) -> str | None:
    lines = frontmatter.split("\n")
    span = _description_span(lines)
    if not span:
        return None
    start, end = span
    first = _DESCRIPTION_KEY.sub("", lines[start], count=1).strip()
    rest = [line.strip() for line in lines[start + 1 : end] if line.strip()]
    if first[:1] in (">", "|"):
        return " ".join(rest)
    value = " ".join([first, *rest])
    if value[:1] == '"':
        try:
            return json.loads(value)
        except ValueError:
            return value.strip('"')
    if value[:1] == "'":
        return value[1:-1].replace("''", "'")
    return value
