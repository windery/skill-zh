import os
import stat

from skill_zh import state


def test_state_dir_is_created_owner_only(env):
    path = state.ensure_state_dir()
    assert os.path.isdir(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o700


def test_log_rotates_past_the_limit(env, monkeypatch):
    monkeypatch.setattr(state, "LOG_MAX_BYTES", 10)
    state.debug_log("第一条，已经超过十个字节了")
    state.debug_log("第二条")
    assert os.path.exists(state.log_path() + ".1")
    with open(state.log_path(), encoding="utf-8") as f:
        assert "第二条" in f.read()


def test_debug_log_never_raises(env, monkeypatch):
    monkeypatch.setenv("SKILL_ZH_STATE_DIR", "/dev/null/not-a-dir")
    state.debug_log("写不进去也不能抛")


def test_records_for_same_name_in_different_roots_do_not_collide(env):
    first = str(env / "skills" / "alpha" / "SKILL.md")
    second = str(env / "other" / "alpha" / "SKILL.md")
    assert state.backup_path(first) != state.backup_path(second)
    assert state.translation_path(first) != state.translation_path(second)
    assert os.path.basename(state.backup_path(first)).startswith("alpha-")


def test_save_and_load_records(env):
    path = str(env / "skills" / "alpha" / "SKILL.md")
    assert state.load_backup(path) is None
    state.save_backup(path, "原件", "译文")
    assert state.load_backup(path) == "原件"
    assert state.load_translation(path) == "译文"


def test_lock_is_exclusive(env):
    with state.exclusive_lock() as first:
        assert first
        with state.exclusive_lock() as second:
            assert not second
    with state.exclusive_lock() as again:
        assert again
