from __future__ import annotations

import json
from pathlib import Path


RULE_DIR = Path(__file__).resolve().parent / "rules"


def load_rule_pack(name: str) -> dict[str, object]:
    path = RULE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_core_rules() -> dict[str, dict[str, object]]:
    return {
        "character_boundary": load_rule_pack("character_boundary"),
        "chapter_commercial_function": load_rule_pack("chapter_commercial_function"),
        "module_protocol": load_rule_pack("module_protocol"),
        "workflow": load_rule_pack("workflow"),
    }


def render_rules_for_prompt() -> str:
    rules = load_core_rules()
    lines: list[str] = []
    for name, payload in rules.items():
        title = payload.get("title", name)
        lines.append(f"### {title}")
        for key in ("principles", "checks", "blocking_rules"):
            values = payload.get(key, [])
            if isinstance(values, list) and values:
                lines.append(f"- {key}: " + "；".join(str(item) for item in values))
        lines.append("")
    return "\n".join(lines).strip()
