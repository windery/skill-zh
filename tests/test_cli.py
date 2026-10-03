import pytest

from conftest import VARIANTS
from skill_zh import __version__, cli
from skill_zh.state import exclusive_lock


def test_status_is_the_default(make_skill, capsys):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("gamma", "---\ndescription: 把会话存到飞书知识库。\n---\n")
    assert cli.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[:2] == ["alpha", "待翻译"]
    assert lines[1].split()[:2] == ["gamma", "本来就是中文"]


def test_status_with_no_skills(env, capsys):
    assert cli.main(["status"]) == 0
    assert "没找到任何 skill" in capsys.readouterr().out


def test_run_is_an_alias_for_translate(env, capsys):
    assert cli.main(["run"]) == 0
    assert "没有需要翻译的 skill" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_translate_while_the_hook_is_already_running(make_skill, capsys):
    make_skill("alpha", VARIANTS["plain"])
    with exclusive_lock():
        assert cli.main(["translate"]) == 0
    assert "后台已经在翻译了" in capsys.readouterr().out
