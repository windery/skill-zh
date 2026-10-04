import os

import pytest

from conftest import VARIANTS
from skill_zh.catalog import Status, classify, discover, is_legacy, legacy_english


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
        "没有简介",
        "空简介",
        "英文",
        "本来就是中文",
        "我们的译文",
        "之后作者更新了",
        "之后用户手动改了",
        "0.2 的双语格式",
    ],
)
def test_classify(description, ours, expected):
    assert classify(description, ours) is expected


def test_legacy_helpers():
    assert is_legacy("中文 ｜ EN: English")
    assert not is_legacy("中文")
    assert not is_legacy(None)
    assert legacy_english("中文 ｜ EN: English text") == "English text"


def test_discover_dedupes_symlinked_skills(env, make_skill, monkeypatch):
    make_skill("alpha", VARIANTS["plain"])
    other = env / "other"
    other.mkdir()
    os.symlink(env / "skills" / "alpha", other / "alpha")
    monkeypatch.setenv("SKILL_ZH_SKILL_DIRS", os.pathsep.join([str(env / "skills"), str(other)]))
    skills = discover()
    assert [s.name for s in skills] == ["alpha"]
    assert skills[0].path == os.path.realpath(env / "skills" / "alpha" / "SKILL.md")


def test_discover_honours_exclude(make_skill):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("beta", VARIANTS["plain"])
    assert [s.name for s in discover(frozenset({"beta"}))] == ["alpha"]


def test_discover_skips_synced_and_system_dirs(make_skill):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("synced", VARIANTS["plain"])
    make_skill(".system", VARIANTS["plain"])
    assert [s.name for s in discover()] == ["alpha"]


def test_discover_reports_missing_description(make_skill):
    make_skill("alpha", "---\nname: a\n---\nbody\n")
    (skill,) = discover()
    assert skill.status is Status.NO_DESCRIPTION
