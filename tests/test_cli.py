import json

import pytest

from conftest import VARIANTS
from skill_zh import __version__, cli, commands
from skill_zh.config import Options
from skill_zh.frontmatter import get_description
from skill_zh.state import exclusive_lock


def test_status_is_the_default(make_skill, capsys):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("gamma", "---\ndescription: 把会话存到飞书知识库。\n---\n")
    make_skill("delta", "---\nname: d\n---\n")
    assert cli.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[:2] == ["alpha", "待翻译"]
    assert lines[1].split()[:2] == ["gamma", "本来就是中文"]
    assert lines[2].split()[:2] == ["delta", "无简介"]
    assert lines[3] == "共 3 个：待翻译 1，本来就是中文 1，无简介 1"


def test_status_tally_always_mentions_pending(make_skill, capsys):
    make_skill("gamma", "---\ndescription: 把会话存到飞书知识库。\n---\n")
    cli.main(["status"])
    assert capsys.readouterr().out.splitlines()[-1] == "共 1 个：待翻译 0，本来就是中文 1"


def test_status_with_no_skills(env, capsys):
    assert cli.main(["status"]) == 0
    assert "没找到任何 skill" in capsys.readouterr().out


def test_version_comes_from_the_manifest(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__
    assert __version__ != "unknown"


def test_translate_while_the_hook_is_already_running(make_skill, capsys):
    make_skill("alpha", VARIANTS["plain"])
    with exclusive_lock():
        assert cli.main(["translate"]) == 0
    assert "后台已经在翻译了" in capsys.readouterr().out


def test_restore_covers_skills_excluded_later(make_skill, fake_translate, monkeypatch, capsys):
    path = make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_EXCLUDE", "alpha")  # 翻完以后才加进 exclude
    assert cli.main(["restore"]) == 0
    assert "已改回英文：alpha" in capsys.readouterr().out
    assert get_description(path.read_text(encoding="utf-8")) == "Do the thing. Use when asked."


def test_manifest_version_matches_changelog():
    from conftest import ROOT

    with open(ROOT / ".claude-plugin" / "plugin.json", encoding="utf-8") as f:
        version = json.load(f)["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {version} - " in changelog
