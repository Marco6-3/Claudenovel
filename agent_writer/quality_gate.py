from __future__ import annotations

import re

from .models import CharacterConstraints, ChapterContract, ReviewIssue


COERCION_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"不.{0,8}就.{0,8}(堵|威胁|曝光|公开|逼)",
        r"(威胁|逼迫|强迫(?!自己)|围观|舆论逼迫|公开羞辱)",
        r"(堵你|堵她|堵在门口|天天堵)",
    )
]

UNAUTHORIZED_SYSTEM_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"系统(任务|奖励|提示|面板)",
        r"(属性点|魅力值|经验值|技能点)\s*[+＋]\s*\d+",
        r"(获得|解锁).{0,12}(被动能力|新技能|新天赋)",
    )
]

AI_FLAVOR_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"一种说不清道不明",
        r"命运的齿轮",
        r"空气仿佛安静",
        r"他知道.*但是他不知道",
    )
]


def _first_match(text: str, patterns: list[re.Pattern[str]]) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def _contains(text: str, needle: str) -> bool:
    cleaned = needle.strip()
    if not cleaned:
        return False
    if cleaned in text:
        return True
    if _semantic_contains(text, cleaned):
        return True
    return _normalize_zh(cleaned) in _normalize_zh(text)


def _normalize_zh(value: str) -> str:
    return re.sub(r"[，。！？、；：“”‘’《》（）\s了]", "", value)


def _semantic_contains(text: str, needle: str) -> bool:
    if "染血校牌" in needle:
        return "校牌" in text and "血" in text and any(token in text for token in ("找", "发现", "躺着", "捡", "翻"))
    if "校牌背面" in needle and "名字" in needle:
        has_name_reveal = any(
            token in text
            for token in ("名字", "姓名", "姓名栏", "三个字", "三道刚被刻")
        )
        return "校牌" in text and "背面" in text and has_name_reveal
    return False


def evaluate_draft(
    draft_text: str,
    contract: ChapterContract,
    constraints: CharacterConstraints,
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []

    payoff_and_ending = {*contract.required_payoffs, contract.ending_hook}
    for idea_lock in contract.idea_contract.idea_locks:
        if idea_lock in payoff_and_ending:
            continue
        if not _contains(draft_text, idea_lock):
            issues.append(
                ReviewIssue(
                    code="missing_idea_lock",
                    severity="blocking",
                    message=f"缺失外部创意锁：{idea_lock}",
                    repair_hint="回到人类提供的外部创意补写该核心要求；不得用另一个点子替代。",
                )
            )

    for forbidden_change in contract.idea_contract.forbidden_changes:
        if _contains(draft_text, forbidden_change):
            issues.append(
                ReviewIssue(
                    code="forbidden_idea_change",
                    severity="blocking",
                    message=f"出现外部创意明确禁止的改动：{forbidden_change}",
                    evidence=forbidden_change,
                    repair_hint="删除该改动，并在 freedom_budget 范围内重新实现原始创意。",
                )
            )

    for payoff in contract.required_payoffs:
        if not _contains(draft_text, payoff):
            issues.append(
                ReviewIssue(
                    code="missing_required_payoff",
                    severity="blocking",
                    message=f"缺失本章必须兑现项：{payoff}",
                    repair_hint="重写核心场景，明确兑现该 payoff，而不是只在旁白中暗示。",
                )
            )

    for beat in contract.forbidden_beats:
        if _contains(draft_text, beat):
            issues.append(
                ReviewIssue(
                    code="forbidden_beat_present",
                    severity="blocking",
                    message=f"出现禁止节点：{beat}",
                    evidence=beat,
                    repair_hint="删除该剧情动作，并用合同允许的冲突替代。",
                )
            )

    coercion = _first_match(draft_text, COERCION_PATTERNS)
    if coercion:
        issues.append(
            ReviewIssue(
                code="coercive_romance",
                severity="blocking",
                message="主角存在胁迫、威胁、公开羞辱或堵人式 romance 风险。",
                evidence=coercion,
                repair_hint="改成角色基于自身目标主动选择，避免用压力制造关系推进。",
            )
        )

    system_change = _first_match(draft_text, UNAUTHORIZED_SYSTEM_PATTERNS)
    if system_change and not contract.allowed_system_changes:
        issues.append(
            ReviewIssue(
                code="unauthorized_system_change",
                severity="blocking",
                message="出现未授权任务、数值、被动能力或系统规则。",
                evidence=system_change,
                repair_hint="删除新增系统文本；如必须新增，先写入章节合同 allowed_system_changes。",
            )
        )

    for character in constraints.characters:
        for action in character.forbidden_actions:
            if _contains(draft_text, action):
                issues.append(
                    ReviewIssue(
                        code="character_boundary_violation",
                        severity="blocking",
                        message=f"{character.name} 越过本章行为边界：{action}",
                        evidence=action,
                        repair_hint="替换成 allowed_actions 中已有依据的行为。",
                    )
                )
        for red_line in character.ooc_red_lines:
            if _contains(draft_text, red_line):
                issues.append(
                    ReviewIssue(
                        code="ooc_red_line",
                        severity="blocking",
                        message=f"{character.name} 触发 OOC 红线：{red_line}",
                        evidence=red_line,
                        repair_hint="回到角色动机、关系阶段和语言风格重写该段。",
                    )
                )

    ending_window = draft_text[-500:]
    if contract.ending_hook and not _contains(ending_window, contract.ending_hook):
        issues.append(
            ReviewIssue(
                code="weak_or_missing_ending_hook",
                severity="risk",
                message="章尾没有清晰落到合同指定尾钩。",
                repair_hint=f"把最后 3-5 段改写到这个新问题上：{contract.ending_hook}",
            )
        )

    ai_flavor = _first_match(draft_text, AI_FLAVOR_PATTERNS)
    if ai_flavor:
        issues.append(
            ReviewIssue(
                code="ai_flavor",
                severity="warning",
                message="出现常见 AI 味表达。",
                evidence=ai_flavor,
                repair_hint="改成更具体的动作、感官或人物口吻。",
            )
        )

    return issues
