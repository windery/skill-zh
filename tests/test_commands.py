import os

from conftest import VARIANTS, body
from skill_zh import commands
from skill_zh.catalog import MAX_DESCRIPTION_LENGTH, Status
from skill_zh.config import Options
from skill_zh.frontmatter import get_description, set_description
from skill_zh.state import backup_path, exclusive_lock, load_backup, load_translation

CHINESE = "---\nname: gamma\ndescription: 把会话存到飞书知识库。\n---\nbody\n"
ENGLISH = "Do the thing. Use when asked."


def statuses():
    return {s.name: s.status for s in commands.status(Options())}


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
    assert get_description(alpha) == "中文说明"  # Chinese only, nothing of the English left
    assert body(alpha) == body(originals["alpha"])
    assert load_backup(real(paths["alpha"])) == originals["alpha"]
    assert load_translation(real(paths["alpha"])) == "中文说明"

    assert sorted(commands.restore(Options())) == ["alpha", "beta"]
    for name, path in paths.items():
        text = path.read_text(encoding="utf-8")
        assert get_description(text) == get_description(originals[name])
        assert body(text) == body(originals[name])
    assert statuses()["alpha"] is Status.PENDING


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
    path.write_text(updated, encoding="utf-8")  # what `npx skills update` does

    assert statuses()["alpha"] is Status.PENDING
    commands.translate_pending(Options(), translate=fake_translate)
    assert fake_translate.calls[-1][0] == {"0:alpha": "Do the new thing. Use when asked."}
    assert load_backup(real(path)) == updated


def test_hand_edited_translation_is_left_alone(make_skill, fake_translate):
    path = make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    edited = set_description(path.read_text(encoding="utf-8"), "我自己改过的说明。")
    path.write_text(edited, encoding="utf-8")

    assert statuses()["alpha"] is Status.ALREADY_CHINESE
    assert commands.restore(Options()) == []
    assert path.read_text(encoding="utf-8") == edited


def test_bilingual_description_is_retranslated_from_the_backup(make_skill, fake_translate):
    original = VARIANTS["plain"]
    path = make_skill("alpha", set_description(original, "一句话概括 ｜ EN: " + ENGLISH))
    backup = backup_path(real(path))
    os.makedirs(os.path.dirname(backup))
    with open(backup, "w", encoding="utf-8") as f:
        f.write(original)  # how 0.1/0.2 left it: backup only, no translation record

    assert statuses()["alpha"] is Status.PENDING
    commands.translate_pending(Options(), translate=fake_translate)

    assert fake_translate.calls[0][0] == {"0:alpha": ENGLISH}
    assert get_description(path.read_text(encoding="utf-8")) == "中文说明"
    assert load_backup(real(path)) == original  # still the untouched original


def test_bilingual_description_without_backup_uses_its_english_half(make_skill, fake_translate):
    path = make_skill("alpha", set_description(VARIANTS["plain"], "一句话概括 ｜ EN: " + ENGLISH))
    commands.translate_pending(Options(), translate=fake_translate)
    assert fake_translate.calls[0][0] == {"0:alpha": ENGLISH}
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
    commands.restore(Options())
    text = path.read_text(encoding="utf-8")
    assert get_description(text) == ENGLISH
    assert text.endswith("Added later.\n")
