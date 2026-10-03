"""
User options and the skill directories skill-zh manages.

Options are declared as ``userConfig`` in ``.claude-plugin/plugin.json``, so
users edit them in ``/config`` instead of a file of our own. Claude Code
exports them to hook processes as ``CLAUDE_PLUGIN_OPTION_<KEY>``. Commands
that Claude runs through the Bash tool (this plugin's skills) don't get those
variables, so we fall back to the ``pluginConfigs`` block Claude Code writes
to the user's settings.json.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from skill_zh.state import claude_config_dir

PLUGIN_NAME = "skill-zh"
DEFAULT_MODEL = "haiku"


@dataclass(frozen=True)
class Options:
    model: str = DEFAULT_MODEL
    exclude: frozenset[str] = field(default_factory=frozenset)


def load_options() -> Options:
    raw = _options_from_env() or _options_from_settings()
    model = str(raw.get("model") or "").strip() or DEFAULT_MODEL
    exclude = frozenset(n.strip() for n in str(raw.get("exclude") or "").split(",") if n.strip())
    return Options(model=model, exclude=exclude)


def _options_from_env() -> dict[str, str]:
    prefix = "CLAUDE_PLUGIN_OPTION_"
    return {k[len(prefix) :].lower(): v for k, v in os.environ.items() if k.startswith(prefix)}


def _options_from_settings() -> dict:
    try:
        with open(os.path.join(claude_config_dir(), "settings.json"), encoding="utf-8") as f:
            configs = json.load(f).get("pluginConfigs") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    # Keyed "plugin@marketplace"; accept whichever marketplace it came from.
    for key, value in configs.items():
        if key.split("@", 1)[0] == PLUGIN_NAME and isinstance(value, dict):
            options = value.get("options")
            return options if isinstance(options, dict) else value
    return {}


def skill_roots() -> list[str]:
    """Global skill directories, one ``<name>/SKILL.md`` per entry.

    Project-level skill directories are left alone on purpose: rewriting them
    would leave a diff in someone's repository. ``SKILL_ZH_SKILL_DIRS``
    (``os.pathsep``-separated) replaces the whole list, for tests and odd setups.
    """
    override = os.environ.get("SKILL_ZH_SKILL_DIRS", "").strip()
    if override:
        return [os.path.expanduser(p) for p in override.split(os.pathsep) if p]
    home = os.path.expanduser("~")
    codex_home = os.environ.get("CODEX_HOME", "").strip() or os.path.join(home, ".codex")
    return [
        os.path.join(home, ".agents", "skills"),  # `npx skills`; shared by most agents
        os.path.join(claude_config_dir(), "skills"),
        os.path.join(os.path.expanduser(codex_home), "skills"),
        os.path.join(home, ".config", "opencode", "skills"),
        os.path.join(home, ".cursor", "skills"),
        os.path.join(home, ".gemini", "skills"),
    ]
