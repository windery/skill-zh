"""判断一段文字算不算中文。catalog 和 translator 都用，所以单独放一个最底层的模块。"""

from __future__ import annotations

import re

_CJK = re.compile("[一-鿿]")
_ENGLISH_WORD = re.compile(r"[A-Za-z]+")


def has_chinese(text: str) -> bool:
    return bool(_CJK.search(text))


def is_mostly_chinese(text: str) -> bool:
    """汉字数不少于英文单词数才算中文。

    只看「有没有汉字」不够：很多英文简介夹着几个中文触发词，对读者来说仍是英文。
    """
    return len(_CJK.findall(text)) >= len(_ENGLISH_WORD.findall(text))
