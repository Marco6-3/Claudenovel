#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Post-generation rewrite pass for webnovel drafts.

This is a small production-facing migration of the useful Kimi Lab idea:
generate first, then run a focused rewrite/evaluation pass that preserves plot
events while tightening style and character behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from runtime_compat import enable_windows_utf8_stdio


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_env_file(path: str | Path | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"env file not found: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _chat(messages: list[dict[str, str]], *, temperature: float, timeout: int) -> tuple[str, str, dict[str, Any]]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY or OPENAI_API_KEY")
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("DEEPSEEK_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or DEFAULT_MODEL
    )
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: HTTP {exc.code} {body[:1200]}") from exc

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"LLM response missing content: {json.dumps(data, ensure_ascii=False)[:1200]}")
    return str(content).strip(), model, data.get("usage") or {}


def build_rewrite_prompt(
    *,
    draft_text: str,
    style_samples: list[str],
    author_settings: str,
    target_chars: str,
) -> str:
    samples = []
    for idx, sample in enumerate(style_samples, start=1):
        samples.append(f"[Style sample {idx}]\n{sample[:3500]}")
    sample_block = "\n\n".join(samples)
    return f"""Rewrite this Chinese webnovel draft.

Rules:
- Preserve the same plot events and payoff. Do not add new plot turns.
- Use only the draft, style samples, and author settings below.
- Tighten prose: cut explanatory psychology, generic romance language, and repeated crowd explanation.
- Improve rhythm: dialogue-forward, shorter paragraphs, crowd jokes after major turns, external action before inner analysis.
- Preserve character boundaries from author settings. If a guarded character made only a limited concession, do not soften it into romance.
- Target length: {target_chars} Chinese characters.
- Output only the rewritten chapter prose.

Author settings:
{author_settings}

{sample_block}

[Draft]
{draft_text}
"""


def local_quality_checks(text: str) -> dict[str, Any]:
    softening_terms = {
        "fate": "命运",
        "yuanfen": "缘分",
        "ripple": "涟漪",
        "heart_move": "心动",
        "warmth": "温暖",
        "different": "不一样",
        "smile_arc": "嘴角",
        "true_heart": "真心",
    }
    qin_sentences = [
        sentence
        for sentence in re.split(r"(?<=[。！？!?])", text)
        if "秦思妍" in sentence
    ]
    qin_help_request = any(
        re.search(r"秦思妍[^。！？!?]{0,40}(帮忙|求助|请求|拜托|需要你)", sentence)
        for sentence in qin_sentences
    )
    dialogue_marks = text.count("“") + text.count("「") + text.count('"')
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    coercion_terms = ("天天堵", "一直堵", "威胁", "舆论", "大家快看", "架在火上", "逼她", "强迫")
    new_power_terms = ("魅力值", "被动能力", "察言观色", "系统奖励", "任务：", "任务:")
    return {
        "chars": len(text),
        "paragraphs": len(paragraphs),
        "avg_paragraph_chars": round(len(text) / max(1, len(paragraphs)), 1),
        "dialogue_marks": dialogue_marks,
        "dialogue_marks_per_1000_chars": round(dialogue_marks * 1000 / max(1, len(text)), 2),
        "contains_contact_payoff": "微信" in text and any(term in text for term in ("添加", "好友", "联系方式", "二维码", "扫码")),
        "qin_help_request": qin_help_request,
        "chen_mo_coercion_risk": any(term in text for term in coercion_terms),
        "new_power_system_risk": any(term in text for term in new_power_terms),
        "softening_counts": {name: text.count(term) for name, term in softening_terms.items()},
    }


def validation_issues(
    checks: dict[str, Any],
    *,
    require_contact_payoff: bool = True,
    max_softening_total: int = 3,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if require_contact_payoff and not checks.get("contains_contact_payoff"):
        issues.append(
            {
                "code": "missing_contact_payoff",
                "severity": "blocking",
                "message": "Chapter does not complete the required WeChat/contact payoff.",
            }
        )
    if checks.get("qin_help_request"):
        issues.append(
            {
                "code": "qin_help_request",
                "severity": "blocking",
                "message": "Qin Siyan appears to request help or initiate dependency too early.",
            }
        )
    if checks.get("chen_mo_coercion_risk"):
        issues.append(
            {
                "code": "chen_mo_coercion_risk",
                "severity": "blocking",
                "message": "Chen Mo appears coercive through blocking, threats, public shaming, or pressure.",
            }
        )
    if checks.get("new_power_system_risk"):
        issues.append(
            {
                "code": "new_power_system_risk",
                "severity": "blocking",
                "message": "Draft appears to introduce a new task/stat/passive-skill system outside the established setting.",
            }
        )
    softening_total = sum(int(v or 0) for v in (checks.get("softening_counts") or {}).values())
    if softening_total > max_softening_total:
        issues.append(
            {
                "code": "over_softening",
                "severity": "warning",
                "message": f"Softening term count is {softening_total}, above threshold {max_softening_total}.",
            }
        )
    return issues


def build_validation_payload(text: str, *, require_contact_payoff: bool = True) -> dict[str, Any]:
    checks = local_quality_checks(text)
    issues = validation_issues(checks, require_contact_payoff=require_contact_payoff)
    blocking = [issue for issue in issues if issue.get("severity") == "blocking"]
    return {
        "ok": not blocking,
        "blocking": bool(blocking),
        "issues": issues,
        "checks": checks,
    }


def cmd_rewrite(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    draft_text = _read_text(args.draft)
    if args.validate_draft:
        validation = build_validation_payload(draft_text, require_contact_payoff=not args.no_require_contact_payoff)
        if validation["blocking"]:
            if args.report_out:
                Path(args.report_out).write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(validation, ensure_ascii=False, indent=2))
            return 1

    style_samples = [_read_text(path) for path in args.style_sample]
    author_settings = _read_text(args.author_settings) if args.author_settings else str(args.author_settings_text or "")
    prompt = build_rewrite_prompt(
        draft_text=draft_text,
        style_samples=style_samples,
        author_settings=author_settings,
        target_chars=args.target_chars,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = Path(args.prompt_out) if args.prompt_out else out_path.with_suffix(".prompt.md")
    prompt_path.write_text(prompt, encoding="utf-8")

    rewritten, model, usage = _chat(
        [
            {"role": "system", "content": "You are a strict Chinese webnovel rewrite editor."},
            {"role": "user", "content": prompt},
        ],
        temperature=float(args.temperature),
        timeout=int(args.timeout),
    )
    out_path.write_text(rewritten, encoding="utf-8")
    report = {
        "model": model,
        "usage": usage,
        "draft_checks": local_quality_checks(draft_text),
        "rewritten_checks": local_quality_checks(rewritten),
        "prompt_file": str(prompt_path),
        "output_file": str(out_path),
    }
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    payload = local_quality_checks(_read_text(args.file))
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = build_validation_payload(
        _read_text(args.file),
        require_contact_payoff=not args.no_require_contact_payoff,
    )
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post-generation rewrite and local quality checks")
    sub = parser.add_subparsers(dest="command", required=True)

    rewrite = sub.add_parser("rewrite")
    rewrite.add_argument("--draft", required=True)
    rewrite.add_argument("--style-sample", action="append", default=[], required=True)
    rewrite.add_argument("--author-settings", default="")
    rewrite.add_argument("--author-settings-text", default="")
    rewrite.add_argument("--target-chars", default="2800-3400")
    rewrite.add_argument("--out", required=True)
    rewrite.add_argument("--report-out", default="")
    rewrite.add_argument("--prompt-out", default="")
    rewrite.add_argument("--env-file", default="")
    rewrite.add_argument("--temperature", type=float, default=0.35)
    rewrite.add_argument("--timeout", type=int, default=300)
    rewrite.add_argument("--validate-draft", action="store_true")
    rewrite.add_argument("--no-require-contact-payoff", action="store_true")
    rewrite.set_defaults(func=cmd_rewrite)

    check = sub.add_parser("check")
    check.add_argument("--file", required=True)
    check.add_argument("--out", default="")
    check.set_defaults(func=cmd_check)

    validate = sub.add_parser("validate")
    validate.add_argument("--file", required=True)
    validate.add_argument("--out", default="")
    validate.add_argument("--no-require-contact-payoff", action="store_true")
    validate.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    enable_windows_utf8_stdio(skip_in_pytest=True)
    raise SystemExit(main())
