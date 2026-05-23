"""Shared output layout helpers for user-facing analysis tasks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class OrganizedOutput:
    task_dir: Path
    data_dir: Path
    report_path: Path


def build_organized_output(
    txt_path: Path,
    task_name: str,
    out_dir: Path | None = None,
    desktop_fallback: bool = False,
) -> OrganizedOutput:
    """Return a stable report/data layout for one analysis task."""

    if out_dir is not None:
        task_dir = out_dir
    else:
        base_dir = _desktop_dir() if desktop_fallback else txt_path.resolve().parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = base_dir / f"claudenovel_{_slugify_task_name(task_name)}_{timestamp}"
    data_dir = task_dir / "data"
    return OrganizedOutput(task_dir=task_dir, data_dir=data_dir, report_path=task_dir / "report.md")


def write_main_report(layout: OrganizedOutput, title: str, body: str, data_dir_label: str = "data") -> None:
    """Write the user-facing report at the task root."""

    layout.task_dir.mkdir(parents=True, exist_ok=True)
    report = [
        f"# {title}\n\n",
        f"> 底座数据目录：`{data_dir_label}`\n\n",
        body.strip(),
        "\n",
    ]
    layout.report_path.write_text("".join(report), encoding="utf-8")


def _desktop_dir() -> Path:
    home = Path.home()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def _slugify_task_name(task_name: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", task_name, flags=re.UNICODE).strip("_")
    return (cleaned[:max_len] or "analysis").strip("_")
