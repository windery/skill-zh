import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BODY = "\n# Title\n\nBody line with description: not a key\n"

# Every description shape found in real skills, each meaning
# "Do the thing. Use when asked." (modulo whitespace).
VARIANTS = {
    "plain": "---\nname: a\ndescription: Do the thing. Use when asked.\n---" + BODY,
    "double-quoted": '---\nname: a\ndescription: "Do the thing. Use when asked."\n---' + BODY,
    "single-quoted": "---\nname: a\ndescription: 'Do the thing. Use when asked.'\n---" + BODY,
    "folded": "---\nname: a\ndescription: >\n  Do the thing.\n  Use when asked.\nmetadata:\n  k: v\n---" + BODY,
    "literal": "---\nname: a\ndescription: |\n  Do the thing.\n  Use when asked.\nlicense: MIT\n---" + BODY,
    "multi-line plain": (
        "---\nname: a\ndescription: Do the thing.\n  Use when asked.\ndisable-model-invocation: true\n---" + BODY
    ),
    "crlf": "---\r\nname: a\r\ndescription: Do the thing. Use when asked.\r\n---\r\n# Title\r\n",
}


def body(text):
    """Everything after the frontmatter."""
    return text.split("---", 2)[2]


@pytest.fixture(params=["pyyaml", "fallback"])
def yaml_mode(request, monkeypatch):
    """Run a test once with PyYAML and once with the built-in fallback parser."""
    if request.param == "pyyaml":
        pytest.importorskip("yaml")
    else:
        monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise ImportError
    return request.param


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate every path skill-zh touches inside tmp_path."""
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("SKILL_ZH_SKILL_DIRS", str(skills))
    monkeypatch.setenv("SKILL_ZH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    for key in list(os.environ):
        if key.startswith("CLAUDE_PLUGIN_OPTION_") or key == "SKILL_ZH_CHILD":
            monkeypatch.delenv(key)
    return tmp_path


@pytest.fixture
def make_skill(env):
    def make(name, text, root="skills"):
        path = env / root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return make


@pytest.fixture
def fake_translate():
    """Stand-in for translator.translate that records calls and never touches the network."""
    calls = []

    def translate(descriptions, model):
        calls.append((dict(descriptions), model))
        return {key: "中文说明" for key in descriptions}

    translate.calls = calls
    return translate
