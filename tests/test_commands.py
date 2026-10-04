import os

import pytest

from conftest import VARIANTS, body
from skill_zh import commands, translator
from skill_zh.catalog import MAX_DESCRIPTION_LENGTH, Status, discover
from skill_zh.config import Options
from skill_zh.frontmatter import get_description, set_description
from skill_zh.state import backup_path, exclusive_lock, load_backup, load_translation

CHINESE = "---\nname: gamma\ndescription: 把会话存到飞书知识库。\n---\nbody\n"
ENGLISH = "Do the thing. Use when asked."


def statuses():
    return {s.name: s.status for s in discover()}


def real(path):
    return str(path.resolve())


def test_translate_then_restore_round_trip(make_skill, fake_translate):
    paths = {"alpha": make_skill("alpha", VARIANTS["folded"]), "beta": make_skill("beta", VARIANTS["double-quoted"])}
    make_skill("gamma", CHINESE)
    originals = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}

    report = commands.translate_pending(Options(model="sonnet"), translate=fake_translate)

    assert sorted(name for name, _ in report.translated) == ["alpha", "beta"]
    assert fake_translate.calls[0][1] == "sonnet"
    assert statuses() == {"alpha": Status.TRANSLATED, "beta": Status.TRANSLATED, "gamma": Status.ALREADY_CHINESE}
    alpha = paths["alpha"].read_text(encoding="utf-8")
    assert get_description(alpha) == "中文说明"  # 只剩中文，英文一点不留
    assert body(alpha) == body(originals["alpha"])
    assert load_backup(real(paths["alpha"])) == originals["alpha"]
    assert load_translation(real(paths["alpha"])) == "中文说明"

    restored = commands.restore()
    assert sorted(restored.restored) == ["alpha", "beta"]
    assert restored.failed == []
    for name, path in paths.items():
        text = path.read_text(encoding="utf-8")
        assert get_description(text) == get_description(originals[name])
        assert body(text) == body(originals[name])
    assert statuses()["alpha"] is Status.PENDING


def test_keys_sent_to_the_model_are_plain_indices(make_skill, fake_translate):
    make_skill("alpha", VARIANTS["plain"])
    make_skill("beta", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    assert fake_translate.calls[0][0] == {"0": ENGLISH, "1": ENGLISH}  # 不带 skill 名和路径


def test_skill_name_with_a_space_translates(make_skill, monkeypatch):
    path = make_skill("my skill", VARIANTS["plain"])
    monkeypatch.setattr(translator, "_call_claude", lambda prompt, model: "@@@ 0\n中文译文\n")
    report = commands.translate_pending(Options())
    assert report.translated == [("my skill", "中文译文")]
    assert get_description(path.read_text(encoding="utf-8")) == "中文译文"


def test_second_run_has_nothing_to_do(make_skill, fake_translate):
    make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    report = commands.translate_pending(Options(), translate=fake_translate)
    assert report.translated == report.failed == []
    assert len(fake_translate.calls) == 1


def test_upstream_update_is_translated_again(make_skill, fake_translate):
    path = make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    updated = VARIANTS["plain"].replace("Do the thing.", "Do the new thing.")
    path.write_text(updated, encoding="utf-8")  # `npx skills update` 做的事

    assert statuses()["alpha"] is Status.PENDING
    commands.translate_pending(Options(), translate=fake_translate)
    assert fake_translate.calls[-1][0] == {"0": "Do the new thing. Use when asked."}
    assert load_backup(real(path)) == updated


def test_file_changed_during_translation_is_left_alone(make_skill):
    path = make_skill("alpha", VARIANTS["plain"])
    updated = VARIANTS["plain"].replace("Do the thing.", "Do the new thing.")

    def translate(descriptions, model):
        path.write_text(updated, encoding="utf-8")  # 翻译进行中，作者更新了 skill
        return dict.fromkeys(descriptions, "中文说明")

    report = commands.translate_pending(Options(), translate=translate)
    assert report.failed == [("alpha", "翻译期间文件被改过，下次再试")]
    assert path.read_text(encoding="utf-8") == updated
    assert load_backup(real(path)) is None
    assert statuses()["alpha"] is Status.PENDING


def test_crlf_file_round_trips_byte_for_byte(make_skill, fake_translate):
    # 走真实的文件读写路径：Python 默认的文本模式会把 CRLF 读成 LF，字符串级的测试发现不了
    path = make_skill("alpha", VARIANTS["crlf mid-field"])
    original = path.read_bytes()
    commands.translate_pending(Options(), translate=fake_translate)
    translated = path.read_bytes()
    assert b"\r\n" in translated
    assert b"\n" not in translated.replace(b"\r\n", b"")
    assert load_backup(real(path)).encode("utf-8") == original  # 备份也得逐字节一致
    commands.restore()
    assert path.read_bytes() == original


def test_bom_file_keeps_its_bom(make_skill, fake_translate):
    path = make_skill("alpha", VARIANTS["bom"])
    commands.translate_pending(Options(), translate=fake_translate)
    assert path.read_bytes().startswith("﻿".encode())
    assert get_description(path.read_text(encoding="utf-8")) == "中文说明"


def test_hand_edited_translation_is_left_alone(make_skill, fake_translate):
    path = make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    edited = set_description(path.read_text(encoding="utf-8"), "我自己改过的说明。")
    path.write_text(edited, encoding="utf-8")

    assert statuses()["alpha"] is Status.ALREADY_CHINESE
    assert commands.restore().restored == []
    assert path.read_text(encoding="utf-8") == edited


def test_bilingual_description_is_retranslated_from_the_backup(make_skill, fake_translate):
    original = VARIANTS["plain"]
    path = make_skill("alpha", set_description(original, "一句话概括 ｜ EN: " + ENGLISH))
    backup = backup_path(real(path))
    os.makedirs(os.path.dirname(backup))
    with open(backup, "w", encoding="utf-8") as f:
        f.write(original)  # 0.1/0.2 留下的样子：只有备份，没有译文记录

    assert statuses()["alpha"] is Status.PENDING
    commands.translate_pending(Options(), translate=fake_translate)

    assert fake_translate.calls[0][0] == {"0": ENGLISH}
    assert get_description(path.read_text(encoding="utf-8")) == "中文说明"
    assert load_backup(real(path)) == original  # 备份仍是未动过的原件


def test_bilingual_description_without_backup_uses_its_english_half(make_skill, fake_translate):
    path = make_skill("alpha", set_description(VARIANTS["plain"], "一句话概括 ｜ EN: " + ENGLISH))
    commands.translate_pending(Options(), translate=fake_translate)
    assert fake_translate.calls[0][0] == {"0": ENGLISH}
    assert get_description(load_backup(real(path))) == ENGLISH


def test_missing_translation_leaves_file_untouched(make_skill):
    path = make_skill("alpha", VARIANTS["plain"])
    before = path.read_text(encoding="utf-8")
    report = commands.translate_pending(Options(), translate=lambda descriptions, model: {})
    assert report.failed == [("alpha", "没拿到译文，下次再试")]
    assert path.read_text(encoding="utf-8") == before
    assert statuses()["alpha"] is Status.PENDING


def test_overlong_translation_is_refused(make_skill):
    path = make_skill("alpha", VARIANTS["plain"])
    before = path.read_text(encoding="utf-8")
    too_long = "长" * (MAX_DESCRIPTION_LENGTH + 1)
    report = commands.translate_pending(
        Options(), translate=lambda descriptions, model: dict.fromkeys(descriptions, too_long)
    )
    assert report.failed == [("alpha", f"译文超过 {MAX_DESCRIPTION_LENGTH} 个字符，保持原样")]
    assert path.read_text(encoding="utf-8") == before


def test_failed_verification_is_reported(make_skill, fake_translate, monkeypatch):
    path = make_skill("alpha", VARIANTS["plain"])
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(commands, "set_description", lambda text, value: None)
    report = commands.translate_pending(Options(), translate=fake_translate)
    assert report.failed == [("alpha", "改写后校验没通过，保持原样")]
    assert path.read_text(encoding="utf-8") == before
    assert load_backup(real(path)) is None


def test_same_name_in_two_roots_keeps_separate_records(env, make_skill, fake_translate, monkeypatch):
    first = make_skill("alpha", VARIANTS["plain"])
    second = make_skill("alpha", VARIANTS["folded"], root="other")
    monkeypatch.setenv("SKILL_ZH_SKILL_DIRS", os.pathsep.join([str(env / "skills"), str(env / "other")]))

    report = commands.translate_pending(Options(), translate=fake_translate)

    assert [name for name, _ in report.translated] == ["alpha", "alpha"]
    assert backup_path(real(first)) != backup_path(real(second))
    assert load_backup(real(first)) == VARIANTS["plain"]
    assert load_backup(real(second)) == VARIANTS["folded"]
    assert commands.restore().restored == ["alpha", "alpha"]


def test_busy_lock_skips_the_run(make_skill, fake_translate):
    make_skill("alpha", VARIANTS["plain"])
    with exclusive_lock() as acquired:
        assert acquired
        report = commands.translate_pending(Options(), translate=fake_translate)
    assert report.busy
    assert fake_translate.calls == []


def test_restore_keeps_later_edits_to_the_body(make_skill, fake_translate):
    path = make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    path.write_text(path.read_text(encoding="utf-8") + "Added later.\n", encoding="utf-8")
    commands.restore()
    text = path.read_text(encoding="utf-8")
    assert get_description(text) == ENGLISH
    assert text.endswith("Added later.\n")


@pytest.mark.skipif(os.geteuid() == 0, reason="root 写只读文件也不会报错")
def test_restore_continues_past_a_file_it_cannot_write(make_skill, fake_translate):
    alpha = make_skill("alpha", VARIANTS["plain"])
    beta = make_skill("beta", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    alpha.chmod(0o444)
    try:
        report = commands.restore()
    finally:
        alpha.chmod(0o644)
    assert report.restored == ["beta"]
    assert [name for name, _ in report.failed] == ["alpha"]
    assert report.failed[0].reason.startswith("写文件失败")
    assert get_description(beta.read_text(encoding="utf-8")) == ENGLISH
