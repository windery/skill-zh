import pytest

from conftest import VARIANTS, body
from skill_zh.frontmatter import get_description, set_description


@pytest.mark.parametrize("kind", VARIANTS)
def test_reads_every_description_shape(kind, yaml_mode):
    assert " ".join(get_description(VARIANTS[kind]).split()) == "Do the thing. Use when asked."


@pytest.mark.parametrize("kind", VARIANTS)
def test_rewrite_changes_only_the_description(kind, yaml_mode):
    text = VARIANTS[kind]
    new = "中文说明 ｜ EN: Do the thing. Use when asked."
    out = set_description(text, new)
    assert out is not None
    assert get_description(out) == new
    assert body(out) == body(text)


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


def test_quotes_and_backslashes_round_trip(yaml_mode):
    new = '中文 "引号" 和 \\ 反斜杠 ｜ EN: say "hi"'
    assert get_description(set_description(VARIANTS["plain"], new)) == new


@pytest.mark.parametrize(
    "text",
    ["# just markdown\n", "---\nname: a\n---\nbody\n", "---\nname: [unclosed\n---\n"],
    ids=["no frontmatter", "no description", "invalid yaml"],
)
def test_refuses_what_it_cannot_rewrite(text):
    assert set_description(text, "x") is None
