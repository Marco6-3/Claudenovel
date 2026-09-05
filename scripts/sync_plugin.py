"""Build/check the standalone plugin from the repository's canonical runtime.

No credentials, novel sources, generated drafts, or experiments are bundled.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "Claudenovel"
SKILLS = ("claudenovel-write", "claudenovel-analyze", "claudenovel-report", "claudenovel-rewrite")


def source_files() -> list[Path]:
    files = [ROOT / name for name in (
        "agent_writer_cli.py", "analyze_enhanced.py", "answer_question.py",
        "rewrite_chapter.py", "index_and_query_rag.py", "benchmark_retrieval.py",
        "requirements.txt", "DEEP_QUESTION_ANSWERING.md", "AGENT_WRITER.md",
        "docs/UNIT_DRAFT_RUNNER.md", "examples/unit_brief.json",
        "docs/research/KIMI_K3_STORY_AND_EMOTION_2026-09-05.md",
    )]
    for package in ("agent_writer", "novel_parser"):
        files.extend(sorted((ROOT / package).glob("*.py")))
    for skill in SKILLS:
        files.extend(sorted(p for p in (ROOT / "skills" / skill).rglob("*") if p.is_file()))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift without changing files")
    args = parser.parse_args()
    sources = source_files()
    for skill in SKILLS:
        if not (ROOT / "skills" / skill / "SKILL.md").is_file():
            raise FileNotFoundError(skill)
    expected = {p.relative_to(ROOT) for p in sources}
    # Refuse stale Python/skill files instead of silently shipping them or deleting edits.
    managed = []
    for folder in ("agent_writer", "novel_parser", "skills"):
        managed.extend(p for p in (PLUGIN / folder).rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts)
    extras = [p.relative_to(PLUGIN) for p in managed if p.relative_to(PLUGIN) not in expected]
    if extras:
        print("Unexpected bundled files: " + ", ".join(map(str, extras)))
        return 1
    drift = []
    for source in sources:
        relative = source.relative_to(ROOT)
        target = PLUGIN / relative
        payload = source.read_bytes()
        if not target.is_file() or target.read_bytes() != payload:
            drift.append(str(relative))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
    if args.check and drift:
        print("Plugin drift: " + ", ".join(drift))
        return 1
    print(f"Plugin {'checked' if args.check else 'synced'}: {len(sources)} source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
