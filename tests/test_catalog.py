import os

import pytest

from conftest import VARIANTS
from skill_zh.catalog import MAX_DESCRIPTION_LENGTH, SEPARATOR, Status, classify, compose, discover, is_mostly_chinese
from skill_zh.config import Options


@pytest.mark.parametrize(
    "text, expected",
    [
        ("把当前会话总结并存到飞书知识库。当用户说「总结会话」时使用。", True),
        ("阅读当前项目或指定 GitHub 仓库的代码，生成文档", True),
        ('Use ChatGPT as the planning brain. Use when the user says "用 ChatGPT 规划".', False),
        ("Diagnose hard bugs.", False),
    ],
)
def test_is_mostly_chinese(text, expected):
    assert is_mostly_chinese(text) is expected


@pytest.mark.parametrize(
    "description, expected",
    [
        (None, Status.NO_DESCRIPTION),
        ("", Status.NO_DESCRIPTION),
        ("中文 ｜ EN: English", Status.TRANSLATED),
        ("把会话存到飞书知识库。", Status.ALREADY_CHINESE),
        ("Diagnose hard bugs.", Status.PENDING),
    ],
)
def test_classify(description, expected):
    assert classify(description) is expected


def test_compose_normalizes_whitespace():
    assert compose("中文", "a  b\n c") == "中文" + SEPARATOR + "a b c"


def test_compose_truncates_summary_never_original():
    original = "x" * 1000
    out = compose("长" * 100, original)
    assert len(out) == MAX_DESCRIPTION_LENGTH
    assert out.endswith(SEPARATOR + original)
    assert "…" in out


def test_compose_gives_up_when_original_fills_the_limit():
    assert compose("中文", "x" * 1010) is None


def test_discover_dedupes_symlinked_skills(env, make_skill, monkeypatch):
    make_skill("alpha", VARIANTS["plain"])
    other = env / "other"
    other.mkdir()
    os.symlink(env / "skills" / "alpha", other / "alpha")
    monkeypatch.setenv("SKILL_ZH_SKILL_DIRS", os.pathsep.join([str(env / "skills"), str(other)]))
    skills = discover(Options())
    assert [s.name for s in skills] == ["alpha"]
    assert skills[0].path == os.path.realpath(env / "skills" / "alpha" / "SKILL.md")


def test_discover_honours_exclude(make_skill):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("beta", VARIANTS["plain"])
    assert [s.name for s in discover(Options(exclude=frozenset({"beta"})))] == ["alpha"]
