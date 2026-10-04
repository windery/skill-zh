"""
用户配置、Claude Code 的配置目录、插件根目录，以及要管的 skill 目录。

配置项在 .claude-plugin/plugin.json 的 userConfig 里声明，用户在 /config 里改，
不用我们自己再维护一个配置文件。Claude Code 会把它们以 CLAUDE_PLUGIN_OPTION_<KEY>
的形式传给钩子进程；但 Claude 通过 Bash 工具运行的命令（本插件的三个 skill）拿不到
这些环境变量，所以再从 settings.json 的 pluginConfigs 里读一遍兜底。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

PLUGIN_NAME = "skill-zh"
# 用同一套核对代理给 30 条真实译文打分：Haiku 有 8 条术语错译或改了触发条件，Sonnet 和 Opus 都是 0，Opus 措辞最顺。
# 翻译量很小（只翻新装或更新的 skill），模型差价可以忽略，所以默认用最好的。
DEFAULT_MODEL = "opus"


def env_path(name: str) -> str | None:
    """读一个路径类环境变量。空值当作没设，免得 shell 配置里写了 `FOO=` 就把路径解析到根目录去。"""
    value = os.environ.get(name, "").strip()
    return os.path.expanduser(value) if value else None


def claude_config_dir() -> str:
    """Claude Code 的配置目录：$CLAUDE_CONFIG_DIR，没设就是 ~/.claude。"""
    return env_path("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def plugin_root() -> str:
    """插件根目录。钩子进程里优先用 Claude Code 传进来的 CLAUDE_PLUGIN_ROOT，否则按本文件位置推算。"""
    return env_path("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class Options:
    model: str = DEFAULT_MODEL
    exclude: frozenset = field(default_factory=frozenset)  # 不翻译的 skill 文件夹名


def load_options() -> Options:
    raw = _options_from_env() or _options_from_settings()
    model = str(raw.get("model") or "").strip() or DEFAULT_MODEL
    exclude = frozenset(n.strip() for n in str(raw.get("exclude") or "").split(",") if n.strip())
    return Options(model=model, exclude=exclude)


def _options_from_env() -> dict:
    prefix = "CLAUDE_PLUGIN_OPTION_"
    return {k[len(prefix) :].lower(): v for k, v in os.environ.items() if k.startswith(prefix)}


def _options_from_settings() -> dict:
    try:
        with open(os.path.join(claude_config_dir(), "settings.json"), encoding="utf-8") as f:
            configs = json.load(f).get("pluginConfigs") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    # 键是「插件名@市场名」，从哪个市场装的都认。
    for key, value in configs.items():
        if key.split("@", 1)[0] == PLUGIN_NAME and isinstance(value, dict):
            options = value.get("options")
            return options if isinstance(options, dict) else value
    return {}


def skill_roots() -> list:
    """全局 skill 目录，每个目录下一个 <名字>/SKILL.md 算一个 skill。

    项目里的 skill 目录故意不管：改了会在别人的仓库里留下 diff。
    SKILL_ZH_SKILL_DIRS（用 os.pathsep 分隔）可以整体替换这个列表，给测试和特殊环境用。
    """
    override = os.environ.get("SKILL_ZH_SKILL_DIRS", "").strip()
    if override:
        return [os.path.expanduser(p) for p in override.split(os.pathsep) if p]
    home = os.path.expanduser("~")
    codex_home = env_path("CODEX_HOME") or os.path.join(home, ".codex")
    return [
        os.path.join(home, ".agents", "skills"),  # `npx skills` 的安装位置，多数工具共用
        os.path.join(claude_config_dir(), "skills"),
        os.path.join(codex_home, "skills"),
        os.path.join(home, ".config", "opencode", "skills"),
        os.path.join(home, ".cursor", "skills"),
        os.path.join(home, ".gemini", "skills"),
    ]
