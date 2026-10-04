import pytest

from conftest import VARIANTS, body
from skill_zh import frontmatter
from skill_zh.frontmatter import copy_description, get_description, set_description


@pytest.mark.parametrize("kind", VARIANTS)
def test_reads_every_description_shape(kind, yaml_mode):
    assert " ".join(get_description(VARIANTS[kind]).split()) == "Do the thing. Use when asked."


@pytest.mark.parametrize("kind", VARIANTS)
def test_rewrite_changes_only_the_description(kind, yaml_mode):
    text = VARIANTS[kind]
    new = "中文说明"
    out = set_description(text, new)
    assert out is not None
    assert get_description(out) == new
    assert body(out) == body(text)


@pytest.mark.parametrize("kind", ["crlf", "crlf mid-field"])
def test_crlf_file_keeps_crlf_everywhere(kind, yaml_mode):
    out = set_description(VARIANTS[kind], "中文说明")
    assert "\r\n" in out
    assert "\n" not in out.replace("\r\n", "")  # 不能冒出孤零零的 LF


def test_bom_is_kept(yaml_mode):
    out = set_description(VARIANTS["bom"], "中文说明")
    assert out.startswith("﻿---\n")
    assert get_description(out) == "中文说明"


@pytest.mark.parametrize("kind", VARIANTS)
def test_copy_description_restores_the_original_bytes(kind, yaml_mode):
    original = VARIANTS[kind]
    translated = set_description(original, "中文说明")
    assert copy_description(translated, original) == translated  # 反过来也成立
    assert copy_description(original, translated) == original


def test_copy_description_refuses_when_either_side_lacks_one():
    assert copy_description("---\nname: a\n---\n", VARIANTS["plain"]) is None
    assert copy_description(VARIANTS["plain"], "# no frontmatter\n") is None


def test_other_fields_survive_byte_for_byte():
    yaml = pytest.importorskip("yaml")
    text = VARIANTS["folded"]
    out = set_description(text, "新简介")
    before = yaml.safe_load(text.split("---")[1])
    after = yaml.safe_load(out.split("---")[1])
    before.pop("description")
    after.pop("description")
    assert before == after
    assert "metadata:\n  k: v\n" in out


def test_verification_catches_a_swallowed_field(yaml_mode, monkeypatch):
    # 假装行范围判断出了错，把紧跟着的 license 字段也吞进了 description
    real_span = frontmatter._description_span
    monkeypatch.setattr(frontmatter, "_description_span", lambda lines: (real_span(lines)[0], real_span(lines)[1] + 1))
    assert set_description(VARIANTS["literal"], "新简介") is None


def test_quotes_and_backslashes_round_trip(yaml_mode):
    new = '中文 "引号" 和 \\ 反斜杠，用户说 "hi" 时使用'
    assert get_description(set_description(VARIANTS["plain"], new)) == new


@pytest.mark.parametrize(
    "text",
    ["# just markdown\n", "---\nname: a\n---\nbody\n", "---\nname: [unclosed\n---\n"],
    ids=["no frontmatter", "no description", "invalid yaml"],
)
def test_refuses_what_it_cannot_rewrite(text):
    assert set_description(text, "x") is None
