import subprocess

from skill_zh import translator


def test_parse_reply_keeps_only_usable_entries():
    batch = {"0": "x", "1": "y", "2": "z"}
    reply = (
        "Sure, here you go:\n```text\n"
        '@@@ 0\n用户说 "debug this" 时使用，\n  跨两行也行\n\n'
        "@@@ 1\nno chinese here\n"
        "@@@ 9\n多余的键\n```\n"
    )
    assert translator.parse_reply(reply, batch) == {"0": '用户说 "debug this" 时使用， 跨两行也行'}


def test_parse_reply_accepts_keys_with_spaces():
    assert translator.parse_reply("@@@  my skill \n中文译文\n", {"my skill": "x"}) == {"my skill": "中文译文"}


def test_parse_reply_rejects_refusals_and_half_translations(env):
    assert translator.parse_reply("@@@ 0\nI cannot translate this. 抱歉\n", {"0": "x"}) == {}
    assert translator.parse_reply("@@@ 0\nUse when the user says 诊断 or debug this\n", {"0": "x"}) == {}


def test_parse_reply_tolerates_garbage(env):
    assert translator.parse_reply("I can't do that.", {"0": "x"}) == {}
    assert translator.parse_reply('{"0": "旧的 JSON 格式"}', {"0": "x"}) == {}


def test_translate_batches_requests(env, monkeypatch):
    prompts = []

    def fake_call(prompt, model):
        prompts.append((prompt, model))
        return "".join(f"@@@ {i}\n译文\n" for i in range(40))

    monkeypatch.setattr(translator, "_call_claude", fake_call)
    descriptions = {str(i): f"English {i}" for i in range(translator.BATCH_SIZE + 1)}
    result = translator.translate(descriptions, "haiku")
    assert len(prompts) == 2
    assert {model for _, model in prompts} == {"haiku"}
    assert result == {key: "译文" for key in descriptions}


def test_failed_batch_is_skipped_not_fatal(env, monkeypatch):
    last = str(translator.BATCH_SIZE)  # 第二批里唯一的键
    replies = iter([subprocess.TimeoutExpired("claude", 1), f"@@@ {last}\n译文\n"])

    def fake_call(prompt, model):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(translator, "_call_claude", fake_call)
    descriptions = {str(i): "English" for i in range(translator.BATCH_SIZE + 1)}
    assert translator.translate(descriptions, "haiku") == {last: "译文"}


def test_missing_claude_binary_translates_nothing(env, monkeypatch):
    monkeypatch.setattr(translator, "find_claude", lambda: None)
    assert translator.translate({"0": "English"}, "haiku") == {}
