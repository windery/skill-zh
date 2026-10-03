"""
Persistent state for skill-zh: the state directory, debug log, run lock and
backups of original SKILL.md files.

State deliberately lives outside the plugin: ``${CLAUDE_PLUGIN_ROOT}`` is
replaced on every update and ``${CLAUDE_PLUGIN_DATA}`` is deleted on
uninstall, but the backups must survive both so ``restore`` keeps working
after the plugin is gone.

Every path is resolved per call rather than cached at import time, so tests
can point the module at a temporary directory through environment variables.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from datetime import datetime
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows has no flock; skill-zh doesn't support it anyway.
    fcntl = None

# Rotate the debug log past this size so it can't grow without bound.
LOG_MAX_BYTES = 1024 * 1024


def _env_path(name: str) -> str | None:
    # An empty value counts as unset, so `FOO=` in a shell profile doesn't
    # silently resolve paths against the filesystem root.
    value = os.environ.get(name, "").strip()
    return os.path.expanduser(value) if value else None


def claude_config_dir() -> str:
    """Claude Code's config directory: ``$CLAUDE_CONFIG_DIR`` or ``~/.claude``."""
    return _env_path("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def state_dir() -> str:
    """Return the state directory.

    Resolution precedence (highest first):
      1. ``SKILL_ZH_STATE_DIR``          — explicit override, used by tests
      2. ``$CLAUDE_CONFIG_DIR/skill-zh``
      3. ``~/.claude/skill-zh``
    """
    return _env_path("SKILL_ZH_STATE_DIR") or os.path.join(claude_config_dir(), "skill-zh")


def _ensure_state_dir() -> str:
    path = state_dir()
    # 0700: backups and logs are nobody else's business on a shared machine.
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def log_path() -> str:
    return os.path.join(state_dir(), "log.txt")


def debug_log(message: str) -> None:
    """Append a timestamped line to the log. Never raises: logging must not break a hook."""
    try:
        _ensure_state_dir()
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
    """Try to become the only process translating; yield whether that worked.

    Several sessions can start at once and each fires the SessionStart hook.
    The lock is a non-blocking ``flock`` so a loser returns immediately instead
    of queueing, and the kernel releases it if the holder dies mid-run.
    """
    if fcntl is None:
        yield True
        return
    fd = os.open(os.path.join(_ensure_state_dir(), "translate.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)  # Closing the descriptor drops the flock.


def backup_path(skill_path: str) -> str:
    """Where the untranslated copy of ``skill_path`` is kept.

    The folder name keeps backups readable; the path hash keeps two skills that
    share a folder name in different roots from overwriting each other.
    """
    digest = hashlib.sha1(skill_path.encode("utf-8")).hexdigest()[:10]
    name = os.path.basename(os.path.dirname(skill_path))
    return os.path.join(state_dir(), "originals", f"{name}-{digest}.md")


def save_backup(skill_path: str, text: str) -> None:
    path = backup_path(skill_path)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def load_backup(skill_path: str) -> str | None:
    try:
        with open(backup_path(skill_path), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None
