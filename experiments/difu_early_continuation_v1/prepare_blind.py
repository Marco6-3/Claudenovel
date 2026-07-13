from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


LABELS = ("A", "B", "C", "D")
SOURCES = ("candidate_01", "candidate_02", "candidate_03", "original")


def prepare_case(public_case_dir: Path, private_case_dir: Path, out_dir: Path) -> Path:
    source_paths = {
        "candidate_01": public_case_dir / "candidates" / "candidate_01.md",
        "candidate_02": public_case_dir / "candidates" / "candidate_02.md",
        "candidate_03": public_case_dir / "candidates" / "candidate_03.md",
        "original": private_case_dir / "private" / "original_target.md",
    }
    missing = [str(path) for path in source_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing blind candidate inputs: {', '.join(missing)}")

    pass_sources = {"forward": SOURCES, "reverse": tuple(reversed(SOURCES))}
    mapping: dict[str, object] = {"case_id": public_case_dir.name, "passes": {}}
    for pass_name, sources in pass_sources.items():
        pass_dir = out_dir / public_case_dir.name / "blind" / pass_name
        pass_dir.mkdir(parents=True, exist_ok=True)
        label_mapping: dict[str, str] = {}
        for label, source in zip(LABELS, sources, strict=True):
            shutil.copyfile(source_paths[source], pass_dir / f"{label}.md")
            label_mapping[label] = source
        mapping["passes"][pass_name] = label_mapping

    mapping_path = out_dir / public_case_dir.name / "_root_mapping.json"
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return mapping_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare counterbalanced anonymous benchmark candidates")
    parser.add_argument("--public-run", type=Path, required=True)
    parser.add_argument("--private-run", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args(argv)
    mappings = [
        prepare_case(args.public_run / case_id, args.private_run / case_id, args.out_dir)
        for case_id in args.case
    ]
    print(json.dumps({"mappings": [str(path) for path in mappings]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
