import os

import pytest

from conftest import VARIANTS
from skill_zh.catalog import Status, classify, discover, is_mostly_chinese
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
    "description, ours, expected",
    [
        (None, None, Status.NO_DESCRIPTION),
        ("", None, Status.NO_DESCRIPTION),
        ("Diagnose hard bugs.", None, Status.PENDING),
        ("把会话存到飞书知识库。", None, Status.ALREADY_CHINESE),
        ("诊断疑难 bug。", "诊断疑难 bug。", Status.TRANSLATED),
        ("Diagnose hard bugs, now faster.", "诊断疑难 bug。", Status.PENDING),
        ("我自己改过的说明。", "诊断疑难 bug。", Status.ALREADY_CHINESE),
        ("诊断 bug ｜ EN: Diagnose hard bugs.", None, Status.PENDING),
    ],
    ids=[
        "missing",
        "empty",
        "english",
        "written in chinese",
        "our translation",
        "updated upstream since",
        "edited by hand since",
        "0.2 bilingual format",
    ],
)
def test_classify(description, ours, expected):
    assert classify(description, ours) is expected


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
