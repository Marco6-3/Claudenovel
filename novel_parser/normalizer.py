"""Text normalization: encoding, alias resolution."""
from __future__ import annotations

import re
from pathlib import Path


ENTITY_ALIASES: dict[str, list[str]] = {
    "陳默": [
        "陈默", "阿默", "陳莫", "陈莫", "陈莫判官", "陳莫判官",
        "主角", "小子",
    ],
    "秦思妍": [
        "思妍", "秦思研", "校花", "女神",
    ],
    "茶茶": [
        "查查看",
    ],
    "判官": [
        "崔判官", "判官大人",
    ],
    "閻王": [
        "阎王", "阎罗王", "閻羅王",
    ],
    "白無常": [
        "白无常", "小白",
    ],
    "黑無常": [
        "黑无常", "小黑",
    ],
    "楊七郎": [
        "杨七郎", "七郎",
    ],
    "王冬": [
        "老王", "冬子",
    ],
    "林蕭": [
        "林萧", "萧萧",
    ],
    "楊晴": [
        "杨晴", "晴晴",
    ],
    "孟婆": [
        "孟婆大人",
    ],
    "富鬼": [
        "富鬼大人",
    ],
    "李天樂": [
        "李天乐", "天樂", "天乐",
    ],
    "小可": [
        "可可",
    ],
    "窮奇": [
        "穷奇",
    ],
    "離淵": [
        "离渊",
    ],
    "刀勞鬼": [
        "刀劳鬼",
    ],
    "胡天霸": [
        "胡天", "天霸",
    ],
    "麥天祐": [
        "麦天佑", "天佑",
    ],
    "董振國": [
        "董振国", "老董",
    ],
    "林正祿": [
        "林正禄", "正禄",
    ],
    "茵茵": [
        "小茵",
    ],
    "九子鬼母": [
        "鬼母",
    ],
    "三瞳鬼母": [],
    "驪山老祖": [
        "骊山老祖",
    ],
    "白龍": [
        "白龙",
    ],
    "虛空尊者": [
        "虚空尊者",
    ],
    "薇薇安": [],
    "魔主": [
        "魔王", "魔尊",
    ],
    "昊天": [
        "天帝",
    ],
    "甄歡喜": [
        "甄欢喜",
    ],
    "尚峰": [],
    "雷妄": [],
    "顧盼": [
        "顾盼",
    ],
    "轉輪王": [
        "转轮王",
    ],
    "夜遊神": [
        "夜游神",
    ],
    "秦廣王": [
        "秦广王",
    ],
}


def read_text(path: Path) -> str:
    """Read text with auto-encoding detection."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "gb18030", "big5", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_aliases(text: str) -> str:
    """Replace all known aliases with canonical names."""
    replacements: list[tuple[str, str]] = []
    for canonical, aliases in ENTITY_ALIASES.items():
        for alias in aliases:
            replacements.append((alias, canonical))
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    for old, new in replacements:
        if new.endswith(old):
            prefix = new[: -len(old)]
            if prefix:
                text = re.sub(rf"(?<!{re.escape(prefix)}){re.escape(old)}", new, text)
                continue
        text = text.replace(old, new)
    return text


def normalize_text(text: str, apply_aliases: bool = True) -> str:
    """Full normalization pipeline."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if apply_aliases:
        text = normalize_aliases(text)
    return text
