"""Enhanced novel analysis entry point."""
from __future__ import annotations

import json
from pathlib import Path

from novel_parser.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_analysis_enhanced"


def main() -> None:
    result = run_pipeline(TXT, OUT)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
