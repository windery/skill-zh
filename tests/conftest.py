import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BODY = "\n# Title\n\nBody line with description: not a key\n"

# 真实 skill 里见过的各种 description 写法，意思都是 "Do the thing. Use when asked."（空白不计）
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
    "crlf mid-field": (
        "---\r\nname: a\r\ndescription: Do the thing. Use when asked.\r\nlicense: MIT\r\n---\r\n# Title\r\n"
    ),
    "bom": "﻿---\nname: a\ndescription: Do the thing. Use when asked.\n---" + BODY,
}


def body(text):
    """frontmatter 之后的全部内容。"""
    return text.split("---", 2)[2]


@pytest.fixture(params=["pyyaml", "fallback"])
def yaml_mode(request, monkeypatch):
    """同一个测试跑两遍：一遍用 PyYAML，一遍用内置的简易解析。"""
    if request.param == "pyyaml":
        pytest.importorskip("yaml")
    else:
        monkeypatch.setitem(sys.modules, "yaml", None)  # 让 `import yaml` 抛 ImportError
    return request.param


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把 skill-zh 会碰的所有路径都隔离到 tmp_path 里。"""
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("SKILL_ZH_SKILL_DIRS", str(skills))
    monkeypatch.setenv("SKILL_ZH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    for key in list(os.environ):
        if key.startswith("CLAUDE_PLUGIN_OPTION_") or key in ("SKILL_ZH_CHILD", "CLAUDE_PLUGIN_ROOT"):
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
    """代替 translator.translate：记录每次调用，不碰网络。"""
    calls = []

    def translate(descriptions, model):
        calls.append((dict(descriptions), model))
        return {key: "中文说明" for key in descriptions}

    translate.calls = calls
    return translate
