import json
import os

import pytest

from conftest import ROOT
from skill_zh.config import DEFAULT_MODEL, load_options, plugin_root, skill_roots
from skill_zh.state import state_dir


def write_settings(env, configs):
    path = env / "claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pluginConfigs": configs}), encoding="utf-8")


def test_defaults(env):
    options = load_options()
    assert options.model == DEFAULT_MODEL
    assert options.exclude == frozenset()


def test_default_model_matches_the_manifest():
    # /config 里显示的默认值来自 plugin.json，代码里的默认值得和它一致
    with open(ROOT / ".claude-plugin" / "plugin.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["userConfig"]["model"]["default"] == DEFAULT_MODEL


def test_options_from_hook_environment(env, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODEL", "sonnet")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_EXCLUDE", " a, b ,,")
    options = load_options()
    assert options.model == "sonnet"
    assert options.exclude == {"a", "b"}


@pytest.mark.parametrize(
    "entry",
    [{"options": {"model": "sonnet", "exclude": "a"}}, {"model": "sonnet", "exclude": "a"}],
    ids=["Claude Code 实际写的格式", "文档示例里的扁平格式"],
)
def test_options_from_settings_when_env_is_missing(env, entry):
    write_settings(env, {"other@x": {"model": "opus"}, "skill-zh@skill-zh": entry})
    options = load_options()
    assert options.model == "sonnet"
    assert options.exclude == {"a"}


def test_environment_wins_over_settings(env, monkeypatch):
    write_settings(env, {"skill-zh@skill-zh": {"model": "opus"}})
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODEL", "sonnet")
    assert load_options().model == "sonnet"


def test_broken_settings_fall_back_to_defaults(env):
    (env / "claude").mkdir()
    (env / "claude" / "settings.json").write_text("{not json", encoding="utf-8")
    assert load_options().model == DEFAULT_MODEL


def test_default_roots_follow_claude_and_codex_homes(env, monkeypatch):
    monkeypatch.delenv("SKILL_ZH_SKILL_DIRS")
    monkeypatch.setenv("CODEX_HOME", str(env / "codex"))
    roots = skill_roots()
    assert str(env / "claude" / "skills") in roots
    assert str(env / "codex" / "skills") in roots
    assert os.path.expanduser("~/.agents/skills") in roots


def test_plugin_root(env, monkeypatch):
    assert plugin_root() == str(ROOT)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(env / "installed"))
    assert plugin_root() == str(env / "installed")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "  ")  # 空值当没设
    assert plugin_root() == str(ROOT)


def test_state_dir_precedence(env, monkeypatch):
    assert state_dir() == str(env / "state")
    monkeypatch.delenv("SKILL_ZH_STATE_DIR")
    assert state_dir() == str(env / "claude" / "skill-zh")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")  # 空值当没设
    assert state_dir() == os.path.expanduser("~/.claude/skill-zh")
