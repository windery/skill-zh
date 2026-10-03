from conftest import VARIANTS, body
from skill_zh import commands
from skill_zh.catalog import SEPARATOR, Status
from skill_zh.config import Options
from skill_zh.frontmatter import get_description
from skill_zh.state import backup_path, exclusive_lock

CHINESE = "---\nname: gamma\ndescription: 把会话存到飞书知识库。\n---\nbody\n"


def statuses():
    return {s.name: s.status for s in commands.status(Options())}


def test_translate_then_restore_round_trip(make_skill, fake_translate):
    paths = {"alpha": make_skill("alpha", VARIANTS["folded"]), "beta": make_skill("beta", VARIANTS["double-quoted"])}
    make_skill("gamma", CHINESE)
    originals = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}

    report = commands.translate_pending(Options(model="sonnet"), translate=fake_translate)

    assert sorted(name for name, _ in report.translated) == ["alpha", "beta"]
    assert fake_translate.calls[0][1] == "sonnet"
    assert statuses() == {"alpha": Status.TRANSLATED, "beta": Status.TRANSLATED, "gamma": Status.ALREADY_CHINESE}
    alpha = paths["alpha"].read_text(encoding="utf-8")
    assert get_description(alpha).startswith("中文说明" + SEPARATOR + "Do the thing.")
    assert body(alpha) == body(originals["alpha"])
    with open(backup_path(str(paths["alpha"].resolve())), encoding="utf-8") as f:
        assert f.read() == originals["alpha"]

    assert sorted(commands.restore(Options())) == ["alpha", "beta"]
    for name, path in paths.items():
        text = path.read_text(encoding="utf-8")
        assert get_description(text) == get_description(originals[name])
        assert body(text) == body(originals[name])


def test_second_run_has_nothing_to_do(make_skill, fake_translate):
    make_skill("alpha", VARIANTS["plain"])
    commands.translate_pending(Options(), translate=fake_translate)
    report = commands.translate_pending(Options(), translate=fake_translate)
    assert report.translated == report.failed == []
    assert len(fake_translate.calls) == 1


def test_missing_translation_leaves_file_untouched(make_skill):
    path = make_skill("alpha", VARIANTS["plain"])
    before = path.read_text(encoding="utf-8")
    report = commands.translate_pending(Options(), translate=lambda descriptions, model: {})
    assert report.failed == [("alpha", "没拿到译文，下次再试")]
    assert path.read_text(encoding="utf-8") == before
    assert statuses()["alpha"] is Status.PENDING


def test_original_too_long_is_reported(make_skill, fake_translate):
    make_skill("alpha", "---\ndescription: " + "word " * 210 + "\n---\n")
    report = commands.translate_pending(Options(), translate=fake_translate)
    assert report.failed == [("alpha", "原简介太长，加不下中文")]


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
    assert get_description(text) == "Do the thing. Use when asked."
    assert text.endswith("Added later.\n")
