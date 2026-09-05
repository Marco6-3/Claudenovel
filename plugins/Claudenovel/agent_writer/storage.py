from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


DIRS = (
    "story_bible",
    "expectations",
    "chapter_contracts",
    "arc_contracts",
    "prompts",
    "drafts",
    "reviews",
    "accepted",
    "commits",
    "state",
    "state/evidence",
    "state/deltas",
    "state/context",
    "state/prompts",
)


def chapter_id(chapter_number: int) -> str:
    return f"chapter_{chapter_number:04d}"


def ensure_project(root: Path) -> Path:
    root = root.resolve()
    for name in DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(read_text(path))


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, payload: BaseModel | dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_text_atomic(path: Path, text: str) -> Path:
    """Replace a UTF-8 file atomically within its destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows sync/indexing services can briefly open the destination
        # without delete sharing. Retry the atomic replace, never unlink the
        # old file or alter its permissions to work around a persistent error.
        for attempt in range(6):
            try:
                os.replace(temp_path, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.025 * (2 ** attempt))
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return path


def write_json_atomic(path: Path, payload: BaseModel | dict[str, object]) -> Path:
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    return write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def read_model(path: Path, model: type[T]) -> T:
    return model.model_validate(read_json(path))


def copy_utf8(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{src} is not valid UTF-8") from exc
    dst.write_text(text, encoding="utf-8")
    return dst


def copy_utf8_atomic(src: Path, dst: Path) -> Path:
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{src} is not valid UTF-8") from exc
    return write_text_atomic(dst, text)


def copy_binary(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst
