from __future__ import annotations

import os
from pathlib import Path


ENV_FILES = (".env", "agent_writer.env", "llm.env")


def load_env(project_root: Path | None = None, *, override: bool = False) -> list[Path]:
    loaded: list[Path] = []
    candidates: list[Path] = []
    if project_root is not None:
        root = project_root.resolve()
        candidates.extend(root / name for name in ENV_FILES)
    candidates.extend(Path.cwd() / name for name in ENV_FILES)
    candidates.append(Path.home() / ".claude" / "Claudenovel" / ".env")
    candidates.append(Path.home() / ".claude" / "webnovel-writer" / ".env")

    seen: set[Path] = set()
    for path in candidates:
        try:
            path = path.resolve()
        except Exception:
            pass
        if path in seen or not path.exists():
            continue
        seen.add(path)
        _load_one(path, override=override)
        loaded.append(path)
    return loaded


def _load_one(path: Path, *, override: bool) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default
