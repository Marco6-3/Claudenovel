from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


DIRS = (
    "story_bible",
    "expectations",
    "chapter_contracts",
    "prompts",
    "drafts",
    "reviews",
    "accepted",
    "commits",
    "state",
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


def copy_binary(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst
