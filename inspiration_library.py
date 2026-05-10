"""CLI entry point for the Claudenovel inspiration case library."""
from __future__ import annotations

from pathlib import Path

from novel_parser.inspiration_library import run_cli


ROOT = Path(__file__).resolve().parent
DEFAULT_LIBRARY_DIR = ROOT / "novel_inspiration_library"


def main() -> None:
    raise SystemExit(run_cli(DEFAULT_LIBRARY_DIR))


if __name__ == "__main__":
    main()
