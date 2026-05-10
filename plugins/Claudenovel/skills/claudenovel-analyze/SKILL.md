---
name: claudenovel-analyze
description: 分析中文小说或小说片段，生成证据化原文包、编辑诊断提示词、人物关系和结构化分析产物。适用于用户说“分析小说”“评价片段”“给后续路线”“让后续改写器能接着改”。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Analyze

## 目标

把用户给出的 `.txt` 或 `.docx` 小说输入转成可供 agent 和 LLM 使用的证据化分析产物。不要只给聊天建议，必须落地文件。

## 输入识别

- 优先使用用户明确给出的文件路径。
- `.txt` 可直接传给 `--txt-path`。
- `.docx` 必须先转换为 UTF-8 `.txt`，再进入分析流程。
- 外部小说必须显式传 `--txt-path`，不要依赖仓库默认文本。
- 如果用户没有指定输出目录，使用输入文件旁边的 `claudenovel_output`，或仓库内 `novel_analysis_enhanced`。

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `analyze_enhanced.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

```powershell
python "<PLUGIN_ROOT>\analyze_enhanced.py" `
  --txt-path "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>" `
  --common-workflow `
  --context-query "评价当前小说片段的优缺点，给出具体、尖锐、可直接改章节的修改建议和后续剧情路线" `
  --context-max-items 160 `
  --context-excerpt-chars 1400
```

如果已知关键角色，加上多个：

```powershell
--focus-entity "主角名" --focus-entity "重要角色名"
```

如果用户只想分析部分章节：

```powershell
--source-start 1 --source-end 20
```

## 关键产物

分析完成后必须检查这些文件：

- `llm_source_pack_detailed.md`
- `llm_source_pack_manifest.json`
- `review_evidence_pack.json`
- `editorial_revision_prompt.md`
- `entity_stats.json`
- `relation_triples.json`
- `sentiment_arc.json`
- `enhanced_briefs.json`

## 验收标准

- `llm_source_pack_detailed.md` 必须包含 `[CHxxx-Pxxx]` 证据编号。
- `editorial_revision_prompt.md` 必须存在，后续深度报告优先使用它。
- 不要声称已生成 LLM 深度报告，除非实际运行了 `claudenovel-report` 或等效 `--llm-context-report`。

## 回复用户

只汇报核心结论、产物路径和下一步建议。不要把大段原文包或提示词全文贴进聊天。
