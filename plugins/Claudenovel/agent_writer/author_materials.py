from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from pydantic import Field

from .models import StrictModel, utc_now_iso
from .storage import (
    ensure_project,
    read_model,
    read_text,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)


MaterialKind = Literal[
    "current_intent",
    "character_design",
    "future_outline",
    "historical_reference",
]

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


class AuthorMaterialRecord(StrictModel):
    material_id: str
    title: str
    kind: MaterialKind
    source_file: str
    source_sha256: str
    imported_file: str
    imported_sha256: str
    note: str = ""
    authority_effect: Literal["reference_only"] = "reference_only"
    context_policy: Literal["explicit_selection_only"] = "explicit_selection_only"
    imported_at: str = Field(default_factory=utc_now_iso)


class AuthorMaterialRegistry(StrictModel):
    schema_version: Literal["author-material-registry/v1"] = "author-material-registry/v1"
    materials: list[AuthorMaterialRecord] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


def material_registry_path(root: Path) -> Path:
    return root / "story_bible" / "source_material" / "registry.json"


def _sha256_binary(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paragraph_text(element: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS)).strip()


def extract_docx_markdown(path: Path) -> str:
    """Extract Word body text in document order using only the standard library."""

    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError(f"docx document body is missing: {path}")
    blocks: list[str] = []
    paragraph_tag = f"{{{WORD_NS}}}p"
    table_tag = f"{{{WORD_NS}}}tbl"
    for child in body:
        if child.tag == paragraph_tag:
            text = _paragraph_text(child)
            if not text:
                continue
            style = child.find("w:pPr/w:pStyle", NS)
            style_value = "" if style is None else style.attrib.get(f"{{{WORD_NS}}}val", "")
            heading_match = re.search(r"(?:Heading|标题)\s*([1-6])", style_value, re.IGNORECASE)
            if heading_match:
                text = "#" * int(heading_match.group(1)) + " " + text
            blocks.append(text)
        elif child.tag == table_tag:
            rows: list[str] = []
            for row in child.findall("w:tr", NS):
                cells = [
                    _paragraph_text(cell).replace("\n", " / ")
                    for cell in row.findall("w:tc", NS)
                ]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append("\n".join(rows))
    return "\n\n".join(blocks).strip() + "\n"


def _material_id(kind: MaterialKind, source_sha256: str) -> str:
    return f"material-{kind}-{source_sha256[:16]}"


def _load_registry(root: Path) -> AuthorMaterialRegistry:
    path = material_registry_path(root)
    if not path.exists():
        return AuthorMaterialRegistry()
    return read_model(path, AuthorMaterialRegistry)


def import_author_materials(
    root: Path,
    *,
    source_files: list[Path],
    kind: MaterialKind,
    note: str = "",
) -> AuthorMaterialRegistry:
    root = ensure_project(root)
    registry = _load_registry(root)
    by_id = {item.material_id: item for item in registry.materials}
    for raw_source in source_files:
        source = raw_source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"author material is missing: {source}")
        suffix = source.suffix.lower()
        if suffix == ".docx":
            text = extract_docx_markdown(source)
            target_name = f"{source.stem}.md"
        elif suffix in {".md", ".txt", ".json"}:
            text = read_text(source)
            target_name = source.name
        else:
            raise ValueError(f"unsupported author material type: {source}")
        source_sha = _sha256_binary(source)
        material_id = _material_id(kind, source_sha)
        target = root / "story_bible" / "source_material" / kind / target_name
        if target.exists() and read_text(target) != text:
            raise ValueError(f"material target differs; refusing overwrite: {target}")
        write_text_atomic(target, text)
        record = AuthorMaterialRecord(
            material_id=material_id,
            title=source.stem,
            kind=kind,
            source_file=str(source),
            source_sha256=source_sha,
            imported_file=str(target),
            imported_sha256=sha256_text(text),
            note=note,
        )
        existing = by_id.get(material_id)
        if existing is not None:
            comparable_existing = existing.model_dump(mode="json", exclude={"imported_at"})
            comparable_record = record.model_dump(mode="json", exclude={"imported_at"})
            if comparable_existing != comparable_record:
                raise ValueError(f"material registry conflict: {material_id}")
            record = existing
        by_id[material_id] = record
    registry.materials = sorted(
        by_id.values(), key=lambda item: (item.kind, item.title, item.material_id)
    )
    registry.updated_at = utc_now_iso()
    write_json_atomic(material_registry_path(root), registry)
    return registry


def render_selected_author_materials(
    root: Path,
    material_ids: list[str] | None,
    *,
    max_chars: int = 50000,
) -> str:
    selected_ids = list(dict.fromkeys(material_ids or []))
    if not selected_ids:
        return "（本单元未显式选择作者材料。）"
    registry = _load_registry(ensure_project(root))
    by_id = {item.material_id: item for item in registry.materials}
    unknown = set(selected_ids) - set(by_id)
    if unknown:
        raise ValueError(f"unknown author material IDs: {sorted(unknown)}")
    sections: list[str] = []
    used = 0
    for material_id in selected_ids:
        item = by_id[material_id]
        text = read_text(Path(item.imported_file))
        section = (
            f"### {item.title}\n"
            f"- material_id: {item.material_id}\n"
            f"- kind: {item.kind}\n"
            f"- authority_effect: {item.authority_effect}\n"
            f"- note: {item.note}\n\n"
            f"{text.strip()}\n"
        )
        used += len(section)
        if used > max_chars:
            raise ValueError(
                f"selected author materials exceed {max_chars} characters; select a smaller set"
            )
        sections.append(section)
    return "\n".join(sections)
