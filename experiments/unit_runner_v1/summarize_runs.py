"""Read-only summary of selected local runs, including interrupted attempts."""
import argparse
import json
from pathlib import Path


def summarize(root: Path):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    usage = [response for p in sorted((root / "usage").glob("*.json")) for response in json.loads(p.read_text(encoding="utf-8"))["responses"]]
    errors = [p.read_text(encoding="utf-8") for p in sorted((root / "responses").glob("*_error.txt"))]
    return {
        "run_id": manifest["run_id"], "path": str(root.resolve()), "status": manifest["status"],
        "logical_calls": manifest["calls"], "returned_responses": len(usage),
        "reported_usage": {key: sum(row.get("usage", {}).get(key, 0) for row in usage) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "reported_elapsed_seconds": round(sum(row.get("elapsed_seconds", 0) for row in usage), 3),
        "body_chars": manifest.get("body_chars"), "selected_revision": manifest.get("selected_revision"),
        "models": manifest["config"]["models"], "validation_errors": errors,
        "code_sha256": manifest["config"]["code_sha256"],
        "usage_note": "Only returned responses are counted; timed-out requests may incur unreported usage.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = json.dumps([summarize(path) for path in args.run_dir], ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
