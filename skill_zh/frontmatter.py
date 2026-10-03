"""
Read and rewrite the ``description`` field of a SKILL.md YAML frontmatter.

Only that one field is touched. Rewriting goes line by line instead of
dumping YAML back out, so comments, key order and quoting style of every
other field survive byte for byte. Every rewrite is verified by parsing the
result again before it is accepted.

PyYAML is used when available. Without it, a small fallback parser
understands the description shapes real skills use: plain, quoted, folded
(``>``), literal (``|``) and multi-line plain scalars.
"""

from __future__ import annotations

import json
import re

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_DESCRIPTION_KEY = re.compile(r"description\s*:")


def get_description(text: str) -> str | None:
    data = _parse(text)
    value = data.get("description") if data else None
    return value if isinstance(value, str) else None


def set_description(text: str, value: str) -> str | None:
    """Return ``text`` with the description replaced, or None if that can't be done safely.

    The new value is written as one double-quoted JSON string, which is also a
    valid YAML double-quoted scalar.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    lines = match.group(1).split("\n")
    span = _description_span(lines)
    if not span:
        return None
    start, end = span
    lines[start:end] = ["description: " + json.dumps(value, ensure_ascii=False)]
    result = text[: match.start(1)] + "\n".join(lines) + text[match.end(1) :]

    before, after = _parse(text), _parse(result)
    if not after or after.get("description") != value:
        return None
    before, after = dict(before or {}), dict(after)
    before.pop("description", None)
    after.pop("description", None)
    return result if before == after else None


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


def _description_span(lines: list[str]) -> tuple[int, int] | None:
    """Line range ``[start, end)`` the description occupies, continuation lines included."""
    for start, line in enumerate(lines):
        if not _DESCRIPTION_KEY.match(line):
            continue
        end = start + 1
        # Continuation lines are indented; blank lines may sit inside block scalars.
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
            end += 1
        # Trailing blank lines belong to whatever comes next, not to the description.
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
