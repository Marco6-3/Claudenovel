"""Structural parsing: volumes, chapters, scenes, dialogues."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


# Scene markers: location keywords that indicate a setting change.
SCENE_MARKERS = [
    "教室", "食堂", "宿舍", "学校", "校园", "校医室", "办公室", "医院",
    "古玩街", "荒地", "雨夜", "华山", "面馆", "活墓", "冥界", "地府",
    "森罗殿", "灵异局", "京海", "房间", "街道", "山上", "山下",
    "宿舍", "教室", "食堂", "图书馆", "校园", "学校", "大学",
    "地府", "酆都", "阴间", "冥界", "黄泉", "奈何桥", "阎王殿",
    "公司", "办公室", "会议室", "工地", "会所", "酒吧", "餐厅",
    "医院", "病房", "诊所",
    "家里", "家中", "别墅", "公寓", "房间", "客厅", "卧室",
    "山上", "山里", "森林", "河边", "河边", "桥下", "洞口",
    "恩施", "苗寨", "土司城", "苗疆", "骊山", "阿尔卑斯", "雪山",
    "微信群", "手机", "红包", "直播间",
]

CHAP_PAT = re.compile(
    r"(?m)^(第[\u4e00-\u9fff〇零一二两三四五六七八九十百千万0-9]+\s*章\s*[^\n\r]*)\s*$"
)
VOL_PAT = re.compile(
    r"(?m)^(第[\u4e00-\u9fff〇零一二两三四五六七八九十百千万0-9]+\s*卷\s*[^\n\r]*)\s*$"
)
# Chinese quotes: 「」 or "" or ''
QUOTE_PAT = re.compile(r"[“”‘’「」\"']([^“”‘’「」\"']{1,300})[“”‘’「」\"']")
# Narrative markers for speaker attribution
SPEAKER_CUES = re.compile(r"([\u4e00-\u9fff]{2,8})(?:说|道|喊|叫|问|答|冷笑|哼|叹|道|说道)")


@dataclass
class Dialogue:
    text: str
    speaker_hint: str = ""          # nearby verb cue like "陳默说"
    preceding_context: str = ""     # ~60 chars before the quote


@dataclass
class Scene:
    location_hint: str = ""         # detected location keyword
    paragraphs: List[str] = field(default_factory=list)
    dialogues: List[Dialogue] = field(default_factory=list)
    chars: int = 0


@dataclass
class Chapter:
    global_index: int
    volume: str
    title: str
    body: str
    chars: int = 0
    first: str = ""
    last: str = ""
    paragraphs: List[str] = field(default_factory=list)
    scenes: List[Scene] = field(default_factory=list)
    dialogues: List[Dialogue] = field(default_factory=list)


def split_paragraphs(body: str) -> List[str]:
    """Split body into meaningful paragraphs."""
    return [
        re.sub(r"\s+", " ", p.strip())
        for p in re.split(r"\n\s*\n", body)
        if len(p.strip()) > 10
    ]


def detect_location(paragraph: str) -> str:
    """Return the first matched scene marker, or empty."""
    for marker in SCENE_MARKERS:
        if marker in paragraph:
            return marker
    return ""


def extract_dialogues(paragraph: str) -> List[Dialogue]:
    """Extract dialogues from a paragraph with speaker hints."""
    dialogues = []
    for m in QUOTE_PAT.finditer(paragraph):
        start = max(0, m.start() - 80)
        ctx = paragraph[start:m.start()]
        speaker = ""
        cue = SPEAKER_CUES.search(ctx)
        if cue:
            speaker = cue.group(1)
        dialogues.append(Dialogue(
            text=m.group(1).strip(),
            speaker_hint=speaker,
            preceding_context=ctx[-60:],
        ))
    return dialogues


def split_scenes(paragraphs: List[str]) -> List[Scene]:
    """Split paragraphs into scenes by location hints."""
    scenes: List[Scene] = []
    current = Scene()
    for para in paragraphs:
        loc = detect_location(para)
        if loc and current.location_hint and loc != current.location_hint:
            if current.paragraphs:
                scenes.append(current)
            current = Scene(location_hint=loc)
        elif loc and not current.location_hint:
            current.location_hint = loc
        current.paragraphs.append(para)
        current.dialogues.extend(extract_dialogues(para))
        current.chars += len(para)
    if current.paragraphs:
        scenes.append(current)
    if not scenes:
        # Fallback: whole chapter as one scene
        scenes.append(Scene(paragraphs=paragraphs, chars=sum(len(p) for p in paragraphs)))
    return scenes


def parse_chapters(text: str) -> List[Chapter]:
    """Parse full text into structured chapters."""
    chap_ms = list(CHAP_PAT.finditer(text))
    vol_ms = list(VOL_PAT.finditer(text))
    chapters: List[Chapter] = []
    for i, m in enumerate(chap_ms):
        start = m.end()
        end = chap_ms[i + 1].start() if i + 1 < len(chap_ms) else len(text)
        body = text[start:end]
        # volume attribution
        vol = ""
        for vm in vol_ms:
            if vm.start() < m.start():
                vol = vm.group(1).strip()
            else:
                break
        paras = split_paragraphs(body)
        scenes = split_scenes(paras)
        all_dialogues = [d for s in scenes for d in s.dialogues]
        chapters.append(Chapter(
            global_index=i + 1,
            volume=vol,
            title=m.group(1).strip(),
            body=body,
            chars=len(body),
            first=paras[0][:260] if paras else "",
            last=paras[-1][-220:] if paras else "",
            paragraphs=paras,
            scenes=scenes,
            dialogues=all_dialogues,
        ))
    return chapters
