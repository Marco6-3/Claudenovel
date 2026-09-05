"""Re-audit an immutable unit using the current evidence-grounded reviewer."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_writer.llm_client import build_client, OpenAICompatibleClient
from agent_writer.storage import read_text, sha256_file, write_json_atomic, write_text_atomic
from agent_writer.unit_runner import UnitBrief, UnitPlan, _review_prompt, _review_validator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--thinking", choices=["enabled", "disabled"])
    args = parser.parse_args()
    if args.out_dir.exists():
        raise ValueError("out-dir must be new; archived audits are not overwritten")
    brief = UnitBrief.model_validate_json(read_text(args.run_dir / "input/brief.json"))
    raw_plan = json.loads(read_text(args.run_dir / "plan.json"))
    for chapter in raw_plan["chapters"]:
        chapter.setdefault("state_before", "历史实验未记录")
        chapter.setdefault("resulting_change", "历史实验未记录")
    plan = UnitPlan.model_validate(raw_plan)
    manifest = json.loads(read_text(args.run_dir / "manifest.json"))
    paths = [args.run_dir / f"chapters/v0/{i:02d}.md" for i in range(1, len(plan.chapters) + 1)]
    # This experiment deliberately targets original v0; revisions are not mixed.
    texts = [read_text(path) for path in paths]
    context = read_text(args.run_dir / "input/context.md")
    prompt = _review_prompt(brief, context, plan, texts)
    write_text_atomic(args.out_dir / "prompt.md", prompt)
    client = build_client(ROOT, role="UNIT_SCORER")
    if args.thinking:
        client = OpenAICompatibleClient(replace(client.config, thinking=args.thinking))
    for attempt in range(2):
        raw = client.complete(prompt, temperature=0.15, max_tokens=16000,
                              max_attempts=2, max_truncation_retries=1, max_empty_retries=0)
        write_text_atomic(args.out_dir / f"raw_{attempt}.txt", raw)
        write_json_atomic(args.out_dir / f"usage_{attempt}.json", {
            "responses": client.last_call_trace,
            "context_checks": client.last_context_trace,
        })
        try:
            review = _review_validator(texts)(raw)
        except ValueError as exc:
            if attempt == 1:
                raise
            prompt += "\n上次校验失败：" + str(exc) + "。请重写完整 JSON，每条引文只复制原文一小句。"
            write_text_atomic(args.out_dir / "repair_prompt.md", prompt)
            continue
        break
    write_json_atomic(args.out_dir / "review.json", review)
    write_json_atomic(args.out_dir / "provenance.json", {
        "source_run_id": manifest["run_id"], "source_version": 0,
        "source_hashes": {str(path): sha256_file(path) for path in paths},
        "model": client.config.model,
        "thinking": client.config.thinking,
        "reasoning_effort": client.config.reasoning_effort,
        "context_window_tokens": client.config.context_window_tokens,
        "reviewer_sha256": sha256_file(ROOT / "agent_writer/unit_runner.py"),
    })
    print(json.dumps(review.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
