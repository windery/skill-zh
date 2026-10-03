import subprocess

from skill_zh import translator


def test_parse_reply_keeps_only_usable_entries():
    batch = {"0:a": "x", "1:b": "y", "2:c": "z"}
    reply = 'Sure!\n{"0:a": "中文 说明\\n", "1:b": "no chinese", "9:z": "多余的键"}\nDone.'
    assert translator.parse_reply(reply, batch) == {"0:a": "中文 说明"}


def test_parse_reply_tolerates_garbage(env):
    assert translator.parse_reply("I can't do that.", {"0:a": "x"}) == {}
    assert translator.parse_reply("[1, 2]", {"0:a": "x"}) == {}


def test_translate_batches_requests(env, monkeypatch):
    prompts = []

    def fake_call(prompt, model):
        prompts.append((prompt, model))
        return "{" + ",".join(f'"{i}": "译文"' for i in range(40)) + "}"

    monkeypatch.setattr(translator, "_call_claude", fake_call)
    descriptions = {str(i): f"English {i}" for i in range(translator.BATCH_SIZE + 1)}
    result = translator.translate(descriptions, "haiku")
    assert len(prompts) == 2
    assert {model for _, model in prompts} == {"haiku"}
    assert result == {key: "译文" for key in descriptions}


def test_failed_batch_is_skipped_not_fatal(env, monkeypatch):
    replies = iter([subprocess.TimeoutExpired("claude", 1), '{"15": "译文"}'])

    def fake_call(prompt, model):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(translator, "_call_claude", fake_call)
    descriptions = {str(i): "English" for i in range(translator.BATCH_SIZE + 1)}
    assert translator.translate(descriptions, "haiku") == {"15": "译文"}


def test_missing_claude_binary_translates_nothing(env, monkeypatch):
    monkeypatch.setattr(translator, "find_claude", lambda: None)
    assert translator.translate({"0:a": "English"}, "haiku") == {}
