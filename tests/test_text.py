import pytest

from skill_zh.text import has_chinese, is_mostly_chinese


@pytest.mark.parametrize(
    "text, expected",
    [
        ("把当前会话总结并存到飞书知识库。当用户说「总结会话」时使用。", True),
        ("阅读当前项目或指定 GitHub 仓库的代码，生成文档", True),
        ('Use ChatGPT as the planning brain. Use when the user says "用 ChatGPT 规划".', False),
        ("Diagnose hard bugs.", False),
        ("I cannot translate this. 抱歉", False),
    ],
)
def test_is_mostly_chinese(text, expected):
    assert is_mostly_chinese(text) is expected


def test_has_chinese():
    assert has_chinese("a 中 b")
    assert not has_chinese("abc")
