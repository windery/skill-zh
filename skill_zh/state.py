"""
持久状态：状态目录、日志、翻译锁，以及每个 skill 的原件和译文记录。

状态故意不放在插件目录里：${CLAUDE_PLUGIN_ROOT} 每次更新都会换，
${CLAUDE_PLUGIN_DATA} 卸载时会被删，而备份得两者都扛得住，卸载后 restore 还要能用。

所有路径都在调用时现算，不在导入时缓存，这样测试可以用环境变量把它们指到临时目录。
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from datetime import datetime
from typing import Iterator

from skill_zh.config import claude_config_dir, env_path

try:
    import fcntl
except ImportError:  # Windows 没有 flock；skill-zh 本来也不支持 Windows
    fcntl = None

# 日志超过这个大小就轮转一次，免得无限增长
LOG_MAX_BYTES = 1024 * 1024


def state_dir() -> str:
    """状态目录。优先级：SKILL_ZH_STATE_DIR（测试用）> $CLAUDE_CONFIG_DIR/skill-zh > ~/.claude/skill-zh。"""
    return env_path("SKILL_ZH_STATE_DIR") or os.path.join(claude_config_dir(), "skill-zh")


def ensure_state_dir() -> str:
    """确保状态目录存在并返回它。新建时权限 0700：备份和日志在共用机器上不该让别人看。"""
    path = state_dir()
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def log_path() -> str:
    return os.path.join(state_dir(), "log.txt")


def debug_log(message: str) -> None:
    """往日志追加一行。永远不抛异常：写日志失败不能把钩子搞挂。"""
    try:
        ensure_state_dir()
        path = log_path()
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                os.replace(path, path + ".1")
        except OSError:
            pass
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


@contextlib.contextmanager
def exclusive_lock() -> Iterator[bool]:
    """争一个「只有我在翻译」的锁，yield 是否争到了。

    几个会话同时打开时，每个都会触发 SessionStart 钩子。用非阻塞的 flock：
    没争到的立刻放弃而不是排队等；持锁进程中途死掉的话，内核会自动释放。
    """
    if fcntl is None:
        yield True
        return
    fd = os.open(os.path.join(ensure_state_dir(), "translate.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)  # 关掉描述符，flock 就释放了


def _record_base(skill_path: str) -> str:
    # 文件夹名让记录可读；路径哈希让不同目录下同名的 skill 不会互相覆盖
    digest = hashlib.sha1(skill_path.encode("utf-8")).hexdigest()[:10]
    name = os.path.basename(os.path.dirname(skill_path))
    return os.path.join(state_dir(), "originals", f"{name}-{digest}")


def backup_path(skill_path: str) -> str:
    """这个 skill 翻译前的完整原件，restore 用它。"""
    return _record_base(skill_path) + ".md"


def translation_path(skill_path: str) -> str:
    """我们写进这个 skill 的译文。

    判断「是不是我们翻的」就靠它：文件里的简介和这份记录一字不差才算已汉化。
    """
    return _record_base(skill_path) + ".zh.txt"


def save_backup(skill_path: str, original_text: str, translation: str) -> None:
    originals = os.path.join(ensure_state_dir(), "originals")
    os.makedirs(originals, mode=0o700, exist_ok=True)
    for path, content in ((backup_path(skill_path), original_text), (translation_path(skill_path), translation)):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def load_backup(skill_path: str) -> str | None:
    return _read(backup_path(skill_path))


def load_translation(skill_path: str) -> str | None:
    return _read(translation_path(skill_path))


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None
