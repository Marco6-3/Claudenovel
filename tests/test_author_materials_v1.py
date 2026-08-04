from __future__ import annotations

import zipfile
from pathlib import Path

from agent_writer.author_materials import import_author_materials
from agent_writer.pipeline import init_project


def _write_minimal_docx(path: Path) -> None:
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>人物档案</w:t></w:r></w:p>
    <w:p><w:r><w:t>秦思妍不是魔尊转世。</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml.encode("utf-8"))


def test_import_docx_as_reference_only_material(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(
        root,
        name="材料导入测试",
        genre="校园修仙",
        premise="学生处理身体异变。",
        target_reader="男频读者",
    )
    source = tmp_path / "秦思妍.docx"
    _write_minimal_docx(source)

    registry = import_author_materials(
        root,
        source_files=[source],
        kind="character_design",
        note="人物设计不是已发生正文事实。",
    )

    assert len(registry.materials) == 1
    item = registry.materials[0]
    assert item.authority_effect == "reference_only"
    assert item.context_policy == "explicit_selection_only"
    output = Path(item.imported_file).read_text(encoding="utf-8")
    assert "# 人物档案" in output
    assert "秦思妍不是魔尊转世" in output
