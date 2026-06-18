from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field

from .models import StrictModel


IntentName = Literal[
    "init_project",
    "outline",
    "revise_outline",
    "plan_chapter",
    "generate_chapter",
    "write_prompt",
    "review_chapter",
    "rewrite_chapter",
    "commit_chapter",
    "status",
    "index_report",
    "unknown",
]


class NLIntent(StrictModel):
    intent: IntentName
    confidence: float = Field(ge=0.0, le=1.0)
    slots: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    requires_author_confirmation: bool = False
    proposed_actions: list[str] = Field(default_factory=list)


GENRE_KEYWORDS = [
    "都市异能",
    "都市脑洞",
    "都市日常",
    "悬疑灵异",
    "悬疑脑洞",
    "规则怪谈",
    "玄幻",
    "修仙",
    "仙侠",
    "科幻",
    "末世",
    "高武",
    "历史脑洞",
    "历史古代",
    "古言",
    "现言",
    "现实题材",
    "狗血言情",
    "青春甜宠",
    "豪门总裁",
    "职场婚恋",
    "无限流",
    "系统流",
    "游戏体育",
    "电竞",
    "西幻",
    "克苏鲁",
]


PROPOSED_ACTIONS: dict[IntentName, list[str]] = {
    "init_project": ["创建 story_bible 与 state 真值层", "写入作者策略和读者期待"],
    "outline": ["创建或更新故事大纲 JSON/Markdown"],
    "revise_outline": ["保存旧版大纲", "写入大纲修订记录", "应用修订"],
    "plan_chapter": ["生成章节合同", "生成角色约束", "生成 prewrite plan"],
    "generate_chapter": ["生成写作任务书", "调用现有 generate 生成正文", "运行审稿门禁"],
    "write_prompt": ["生成写作任务书"],
    "review_chapter": ["运行本地质量门禁"],
    "rewrite_chapter": ["生成返修 brief", "调用现有 rewrite 返修正文", "重新运行审稿门禁"],
    "commit_chapter": ["检查明确确认", "检查 review blocking", "提交已接受章节并更新状态索引"],
    "status": ["读取当前项目状态"],
    "index_report": ["读取索引报告和 blocking 问题"],
    "unknown": [],
}


REQUIRED_FIELDS: dict[IntentName, list[str]] = {
    "init_project": ["name", "genre", "premise", "target_reader"],
    "outline": ["logline", "volume_title", "chapter_end", "core_conflict", "climax"],
    "revise_outline": [],
    "plan_chapter": ["chapter_number", "chapter_title", "chapter_goal", "payoffs", "ending_hook"],
    "generate_chapter": ["chapter_number"],
    "write_prompt": ["chapter_number"],
    "review_chapter": ["chapter_number"],
    "rewrite_chapter": ["chapter_number"],
    "commit_chapter": ["chapter_number", "confirmed"],
    "status": [],
    "index_report": [],
    "unknown": [],
}


ZH_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_nl_intent(request: str) -> NLIntent:
    text = _normalize_request(request)
    slots = _extract_slots(text)
    intent, confidence = _classify_intent(text)
    if intent == "outline":
        _fill_outline_defaults(slots)
    if intent == "init_project" and not slots.get("premise"):
        _fill_init_premise(slots)

    safety_warnings = _detect_safety_warnings(text)
    missing_fields = _missing_fields(intent, slots)
    return NLIntent(
        intent=intent,
        confidence=confidence,
        slots=slots,
        missing_fields=missing_fields,
        safety_warnings=safety_warnings,
        requires_author_confirmation=intent == "commit_chapter",
        proposed_actions=list(PROPOSED_ACTIONS[intent]),
    )


def _normalize_request(request: str) -> str:
    return re.sub(r"\s+", " ", request.strip())


def _classify_intent(text: str) -> tuple[IntentName, float]:
    lower = text.lower()

    if _has_commit_confirmation(text, lower):
        return "commit_chapter", 0.92
    if re.search(r"(索引|index|blocking|门禁报告)", lower):
        return "index_report", 0.86
    if re.search(r"(状态|进度|当前项目|现在到哪|status)", lower):
        return "status", 0.86
    if re.search(r"(审稿|审查|检查|质量门禁|ooc|爽点不足|问题)", lower):
        return "review_chapter", 0.88
    if re.search(r"(返修|重写|修一版|改一版|按审稿意见|rewrite)", lower):
        return "rewrite_chapter", 0.88
    if re.search(r"(写作任务书|任务书|提示词|prompt|write prompt)", lower):
        return "write_prompt", 0.88
    if re.search(r"(生成|写|起草|产出).{0,12}(正文|草稿|第\s*[\d一二两三四五六七八九十百零〇]+\s*章)", lower):
        return "generate_chapter", 0.84
    if re.search(r"(规划|计划|章纲|章节合同).{0,12}第\s*[\d一二两三四五六七八九十百零〇]+\s*章", text):
        return "plan_chapter", 0.9
    if re.search(r"第\s*[\d一二两三四五六七八九十百零〇]+\s*章.{0,12}(规划|计划|章纲|章节合同)", text):
        return "plan_chapter", 0.86
    if re.search(r"(修订|修改|调整|重做|改).{0,8}(大纲|总纲|卷纲|outline)", lower):
        return "revise_outline", 0.86
    if re.search(r"(大纲|总纲|卷纲|第一卷|第\s*[\d一二两三四五六七八九十百零〇]+\s*卷|outline)", lower):
        return "outline", 0.82
    if re.search(r"(创建|新建|初始化|开一本|做一本).{0,12}(小说|书|项目)", lower):
        return "init_project", 0.86
    return "unknown", 0.2


def _has_commit_confirmation(text: str, lower: str) -> bool:
    if re.search(r"(commit|提交)", lower) and re.search(r"(章|本章|这一章|当前章|同意|确认|批准|approve)", lower):
        return True
    return bool(re.search(r"(我)?(确认|同意|批准|approve).{0,8}(提交|接受|收稿)", lower))


def _extract_slots(text: str) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    chapter_number = _extract_number_after_unit(text, "章")
    if chapter_number is not None:
        slots["chapter_number"] = chapter_number
    volume_number = _extract_number_after_unit(text, "卷")
    if volume_number is not None:
        slots["volume_number"] = volume_number

    book_name = _extract_book_name(text)
    if book_name:
        slots["name"] = book_name

    genre = _extract_genre(text)
    if genre:
        slots["genre"] = genre

    protagonist_role = _extract_short_value(text, ["主角是", "男主是", "女主是"])
    if protagonist_role:
        slots["protagonist_role"] = protagonist_role

    core_hook = _extract_long_value(text, ["核心钩子", "钩子", "核心卖点"])
    if core_hook:
        slots["core_hook"] = core_hook
    premise = _extract_long_value(text, ["故事前提", "前提", "设定", "一句话故事", "logline"])
    if premise:
        slots["premise"] = premise
        slots.setdefault("logline", premise)
    elif core_hook:
        slots["premise"] = core_hook
        slots.setdefault("logline", core_hook)

    target_reader = _extract_short_value(text, ["目标读者", "读者定位", "面向"])
    if target_reader:
        slots["target_reader"] = target_reader

    theme = _extract_short_value(text, ["主题"])
    if theme:
        slots["theme"] = theme

    volume_title = _extract_short_value(text, ["卷名", "第一卷标题", "卷标题"])
    if volume_title:
        slots["volume_title"] = volume_title

    chapter_end = _extract_chapter_end(text)
    if chapter_end is not None:
        slots["chapter_end"] = chapter_end
    chapter_start = _extract_labeled_number(text, ["起始章节", "从第"])
    if chapter_start is not None:
        slots["chapter_start"] = chapter_start

    core_conflict = _extract_long_value(text, ["核心冲突", "卷冲突", "主冲突"])
    if core_conflict:
        slots["core_conflict"] = core_conflict
    climax = _extract_long_value(text, ["高潮", "卷末高潮", "结局爆点"])
    if climax:
        slots["climax"] = climax

    chapter_title = _extract_chapter_title(text)
    if chapter_title:
        slots["chapter_title"] = chapter_title
    chapter_goal = _extract_long_value(text, ["章节目标", "本章目标", "目标"])
    if not chapter_goal and "chapter_number" in slots:
        chapter_goal = _extract_goal_after_chapter(text)
    if chapter_goal:
        slots["chapter_goal"] = chapter_goal

    payoffs = _extract_list_value(text, ["payoff", "必须兑现", "兑现", "爽点", "收益"])
    if payoffs:
        slots["payoffs"] = payoffs

    ending_hook = _extract_long_value(text, ["ending hook", "章尾钩子", "结尾钩子", "尾钩"])
    if ending_hook:
        slots["ending_hook"] = ending_hook

    characters = _extract_characters(text)
    if characters:
        slots["characters"] = characters

    forbidden = _extract_forbidden(text)
    if forbidden:
        slots["forbidden_beats"] = forbidden
        slots["forbidden_directions"] = forbidden

    if _has_commit_confirmation(text, text.lower()):
        slots["confirmed"] = True
    if re.search(r"(这一章|本章|当前章|这章)", text):
        slots["current_chapter_reference"] = True
    return slots


def _fill_outline_defaults(slots: dict[str, Any]) -> None:
    if slots.get("volume_number") and not slots.get("volume_title"):
        slots["volume_title"] = f"第{slots['volume_number']}卷"
    slots.setdefault("chapter_start", 1)


def _fill_init_premise(slots: dict[str, Any]) -> None:
    parts = []
    if slots.get("protagonist_role"):
        parts.append(f"主角是{slots['protagonist_role']}")
    if slots.get("core_hook"):
        parts.append(f"核心钩子是{slots['core_hook']}")
    if parts:
        slots["premise"] = "；".join(parts)
        slots.setdefault("logline", slots["premise"])


def _extract_number_after_unit(text: str, unit: str) -> int | None:
    match = re.search(rf"第?\s*([0-9一二两三四五六七八九十百零〇]+)\s*{unit}", text)
    if not match:
        return None
    return _parse_number(match.group(1))


def _extract_labeled_number(text: str, labels: list[str]) -> int | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*([0-9一二两三四五六七八九十百零〇]+)", text)
        if match:
            return _parse_number(match.group(1))
    return None


def _parse_number(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if not value:
        return None
    if "百" in value:
        left, _, right = value.partition("百")
        hundreds = _parse_number(left) if left else 1
        rest = _parse_number(right) if right else 0
        if hundreds is None or rest is None:
            return None
        return hundreds * 100 + rest
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _parse_number(left) if left else 1
        ones = _parse_number(right) if right else 0
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    total = 0
    for char in value:
        if char not in ZH_DIGITS:
            return None
        total = total * 10 + ZH_DIGITS[char]
    return total


def _extract_book_name(text: str) -> str:
    patterns = [
        r"(?:书名|小说名|项目名)(?:是|叫|为|：|:)\s*[《“\"]?([^》”\"，。；;]+)",
        r"(?:创建|新建|开)(?:一?本|一?部)?.{0,12}小说[，, ]+(?:叫|名为)\s*[《“\"]?([^》”\"，。；;]+)",
    ]
    return _first_group(text, patterns)


def _extract_genre(text: str) -> str:
    for genre in sorted(GENRE_KEYWORDS, key=len, reverse=True):
        if genre in text:
            return genre
    match = re.search(r"(?:创建|新建|初始化|开|做)(?:一?本|一?部)?\s*([一-龥A-Za-z0-9_-]{2,12})小说", text)
    return match.group(1).strip() if match else ""


def _extract_short_value(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"(?:{re.escape(label)})(?:是|为|叫|：|:)?\s*([^，。；;\n]+)", text, flags=re.IGNORECASE)
        if match:
            return _clean_value(match.group(1))
    return ""


def _extract_long_value(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"(?:{re.escape(label)})(?:是|为|叫|：|:)?\s*([^。；;\n]+)", text, flags=re.IGNORECASE)
        if match:
            return _clean_value(match.group(1))
    return ""


def _extract_list_value(text: str, labels: list[str]) -> list[str]:
    raw = _extract_long_value(text, labels)
    if not raw:
        return []
    return [item for item in (_clean_value(v) for v in re.split(r"[、,，/；;]|和|与", raw)) if item]


def _extract_chapter_title(text: str) -> str:
    patterns = [
        r"第\s*[0-9一二两三四五六七八九十百零〇]+\s*章[《“\"]([^》”\"]+)[》”\"]",
        r"(?:章名|章节标题|标题)(?:是|为|叫|：|:)\s*[《“\"]?([^》”\"，。；;]+)",
    ]
    return _first_group(text, patterns)


def _extract_goal_after_chapter(text: str) -> str:
    match = re.search(r"第\s*[0-9一二两三四五六七八九十百零〇]+\s*章[，, ]+([^。；;\n]+)", text)
    if not match:
        return ""
    value = _clean_value(match.group(1))
    value = re.sub(r"^(正文|草稿|审稿|返修|重写|写作任务书)\s*", "", value)
    return value


def _extract_chapter_end(text: str) -> int | None:
    patterns = [
        r"(?:共|写|规划|做到|到|章节数|章数)\s*([0-9一二两三四五六七八九十百零〇]+)\s*章",
        r"([0-9一二两三四五六七八九十百零〇]+)\s*章(?:左右|以内|篇幅|体量)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _parse_number(match.group(1))
    return None


def _extract_characters(text: str) -> list[str]:
    values: list[str] = []
    listed = _extract_list_value(text, ["出场角色", "主要角色", "角色", "人物"])
    values.extend(listed)
    for pattern in (
        r"(?:主角|男主|女主|反派)(?:叫|名叫)\s*([^，。；;\n]+)",
        r"(?:主角名|男主名|女主名)(?:是|为|叫|：|:)\s*([^，。；;\n]+)",
    ):
        match = re.search(pattern, text)
        if match:
            values.append(_clean_value(match.group(1)))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _extract_forbidden(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?:不能|不要|禁止)\s*([^，。；;\n]+)", text):
        value = _clean_value(match.group(1))
        if value:
            values.append(value)
    return values


def _detect_safety_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    style_match = re.search(r"(?:模仿|仿写|照着|按|用|学习).{0,20}(?:文风|风格|笔法|口吻)", text)
    if style_match and not re.search(r"(高层|抽象|概括|非仿写)", text):
        warnings.append("检测到模仿具体作者或作品文风的请求：只能提炼高层风格特征，不能生成仿写文本。")
    if re.search(r"(照搬|搬运|复刻|复现|抄|原文|逐字|一比一|照着.+正文)", text):
        warnings.append("检测到搬运或复刻已有作品正文的请求：不能复制或改写受版权保护文本。")
    return warnings


def _missing_fields(intent: IntentName, slots: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field_name in REQUIRED_FIELDS[intent]:
        value = slots.get(field_name)
        if value is None or value == "" or value == [] or value is False:
            missing.append(field_name)
    return missing


def _first_group(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_value(match.group(1))
    return ""


def _clean_value(value: object) -> str:
    text = str(value).strip()
    text = text.strip(" \t\r\n：:，,。；;“”\"《》")
    return _trim_at_next_label(text)


def _trim_at_next_label(text: str) -> str:
    next_label = re.search(
        r"[，,]\s*(?:书名|小说名|项目名|目标读者|读者定位|面向|主题|卷名|第一卷标题|卷标题|"
        r"核心冲突|卷冲突|主冲突|高潮|卷末高潮|结局爆点|章节目标|本章目标|目标|"
        r"payoff|必须兑现|兑现|爽点|收益|ending hook|章尾钩子|结尾钩子|尾钩|"
        r"出场角色|主要角色|角色|人物)(?:是|为|叫|：|:)",
        text,
        flags=re.IGNORECASE,
    )
    if next_label:
        return text[: next_label.start()].strip()
    return text
