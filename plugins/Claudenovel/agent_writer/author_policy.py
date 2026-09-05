from __future__ import annotations

from pathlib import Path

from .models import (
    AuthorPolicyBundle,
    AuthorPolicyProfile,
    AuthorPolicyRule,
    AuthorPolicyTarget,
    utc_now_iso,
)
from .novel_state import load_novel_state
from .storage import ensure_project, read_model, write_json_atomic


def author_policy_path(root: Path) -> Path:
    return root / "story_bible" / "author_policy_v1.json"


def _rule_semantic_dump(rule: AuthorPolicyRule) -> dict[str, object]:
    return rule.model_dump(mode="json", exclude={"created_at"})


def initialize_author_policy(root: Path) -> AuthorPolicyProfile:
    root = ensure_project(root)
    state = load_novel_state(root)
    profile = AuthorPolicyProfile(project_id=state.project_id)
    write_json_atomic(author_policy_path(root), profile)
    return profile


def load_author_policy(root: Path) -> AuthorPolicyProfile:
    root = ensure_project(root)
    path = author_policy_path(root)
    if path.exists():
        return read_model(path, AuthorPolicyProfile)
    return initialize_author_policy(root)


def add_author_policy_rule(
    root: Path,
    rule: AuthorPolicyRule,
    *,
    replace: bool = False,
) -> AuthorPolicyProfile:
    root = ensure_project(root)
    profile = load_author_policy(root)
    existing_index = next(
        (index for index, item in enumerate(profile.rules) if item.rule_id == rule.rule_id),
        None,
    )
    if existing_index is not None:
        existing = profile.rules[existing_index]
        if _rule_semantic_dump(existing) == _rule_semantic_dump(rule):
            return profile
        if not replace:
            raise ValueError(f"author policy rule already exists: {rule.rule_id}")
        profile.rules[existing_index] = rule
    else:
        profile.rules.append(rule)
    profile.revision += 1
    profile.updated_at = utc_now_iso()
    write_json_atomic(author_policy_path(root), profile)
    return profile


def import_author_policy_bundle(
    root: Path,
    bundle_file: Path,
    *,
    replace: bool = False,
) -> AuthorPolicyProfile:
    root = ensure_project(root)
    bundle = read_model(bundle_file, AuthorPolicyBundle)
    profile = load_author_policy(root)
    by_id = {rule.rule_id: rule for rule in profile.rules}
    changed = False
    for rule in bundle.rules:
        existing = by_id.get(rule.rule_id)
        if existing is None:
            profile.rules.append(rule)
            by_id[rule.rule_id] = rule
            changed = True
            continue
        if _rule_semantic_dump(existing) == _rule_semantic_dump(rule):
            continue
        if not replace:
            raise ValueError(f"author policy rule already exists: {rule.rule_id}")
        index = next(
            index for index, item in enumerate(profile.rules) if item.rule_id == rule.rule_id
        )
        profile.rules[index] = rule
        by_id[rule.rule_id] = rule
        changed = True
    if changed:
        profile.revision += 1
        profile.updated_at = utc_now_iso()
        write_json_atomic(author_policy_path(root), profile)
    return profile


def active_author_policy_rules(
    root: Path,
    *,
    role: AuthorPolicyTarget | None = None,
) -> list[AuthorPolicyRule]:
    profile = load_author_policy(root)
    return [
        rule
        for rule in profile.rules
        if rule.active and (role is None or role in rule.applies_to)
    ]


def render_author_policy(
    root: Path,
    *,
    role: AuthorPolicyTarget,
) -> str:
    profile = load_author_policy(root)
    rules = active_author_policy_rules(root, role=role)
    lines = [
        f"- AuthorPolicy revision：{profile.revision}",
        "- 以下规则全部为 author_locked；模型不得用正文惯例、商业小说范例或自身偏好覆盖。",
    ]
    if not rules:
        lines.append("- （作者尚未为该角色录入额外偏好。）")
        return "\n".join(lines)
    for rule in rules:
        lines.append(
            f"- [{rule.severity}] [{rule.category}] {rule.rule_id}: {rule.instruction}"
        )
        if rule.rationale:
            lines.append(f"  - 原因：{rule.rationale}")
        if rule.avoid_examples:
            lines.append("  - 避免示例：" + "；".join(rule.avoid_examples))
        if rule.preferred_examples:
            lines.append("  - 倾向示例：" + "；".join(rule.preferred_examples))
        if rule.source_refs:
            lines.append("  - 来源：" + "；".join(rule.source_refs))
    return "\n".join(lines)
