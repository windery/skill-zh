import io
import json
import subprocess
import sys

import pytest

from conftest import ROOT, VARIANTS
from skill_zh import hook


@pytest.mark.parametrize(
    "command, expected",
    [
        ("npx skills add owner/repo -g", True),
        ("npx skills update", True),
        ("bunx skills install x", True),
        ("cp -r foo ~/.agents/skills/", True),
        ("git clone https://x/y ~/.claude/skills/y", True),
        ("ls -la", False),
        ("git status", False),
        ("npm install", False),
        ("python3 run.py --update", False),
    ],
)
def test_post_tool_use_filters_bash_commands(command, expected):
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    assert hook.should_run(payload) is expected


def test_session_start_always_runs():
    assert hook.should_run({"hook_event_name": "SessionStart", "source": "startup"})


@pytest.fixture
def runs(monkeypatch):
    calls = []
    monkeypatch.setattr(hook, "spawn_translation", lambda: calls.append(True))
    return calls


def test_translates_when_something_is_pending(make_skill, runs):
    make_skill("alpha", VARIANTS["plain"])
    hook.main(io.StringIO(json.dumps({"hook_event_name": "SessionStart"})))
    assert len(runs) == 1


def test_stays_quiet_when_nothing_is_pending(make_skill, runs):
    make_skill("gamma", "---\ndescription: 把会话存到飞书知识库。\n---\n")
    hook.main(io.StringIO(json.dumps({"hook_event_name": "SessionStart"})))
    assert runs == []


def test_ignored_inside_its_own_translation_call(make_skill, runs, monkeypatch):
    make_skill("alpha", VARIANTS["plain"])
    monkeypatch.setenv("SKILL_ZH_CHILD", "1")
    hook.main(io.StringIO(json.dumps({"hook_event_name": "SessionStart"})))
    assert runs == []


def test_spawned_translation_is_detached_and_runnable(env, monkeypatch):
    spawned = {}
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: spawned.update(args=args, **kwargs))
    hook.spawn_translation()
    monkeypatch.setattr(subprocess, "Popen", real_popen)
    assert spawned["start_new_session"] is True
    assert spawned["args"][1:] == [str(ROOT / "skill_zh"), "translate"]

    # Replay the exact command in the foreground: run from the state dir, with
    # no PYTHONPATH help, it must still import the package and run cleanly.
    proc = subprocess.run(spawned["args"], cwd=spawned["cwd"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "没有需要翻译的 skill" in proc.stdout


@pytest.mark.parametrize("stdin", ["", "not json", "[]"])
def test_entry_script_always_exits_zero(env, stdin):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "translate_hook.py")],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
