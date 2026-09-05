---
name: claudenovel-analyze
description: 为写作和改稿分析中文小说或片段，生成证据化原文包、人物关系与编辑诊断提示词，或核对具体文学问题。适用于“分析前文”“评价片段”“检查人物感情线”。写完整单元使用 claudenovel-write。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Analyze

## 目标

把用户给出的 `.txt` 或 `.docx` 小说输入转成可供 agent 和 LLM 使用的证据化分析产物。不要只给聊天建议，必须落地文件。

本技能是按需分析工具，不是写作前置步骤。用户要求直接按方案写作时，使用 `claudenovel-write`。
所有命令使用 `python -X utf8`；长中文问题与方案优先通过 UTF-8 文件准备，避免 shell 编码损坏。
根据本 SKILL.md 位置向上两级定位插件根目录，输出放在插件缓存之外。只评价文本时不调用写作或提交命令。

## 输入识别

- 优先使用用户明确给出的文件路径。
- `.txt` 可直接传给 `--txt-path`。
- `.docx` 必须先转换为 UTF-8 `.txt`，再进入分析流程。
- 外部小说必须显式传 `--txt-path`，不要依赖仓库默认文本。
- 如果用户没有指定输出目录，使用输入文件旁边自动生成的任务文件夹；也可显式放在桌面。
- 每次分析必须使用统一输出布局：任务文件夹根目录放 `report.md`，底座数据统一放 `data/`。

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `analyze_enhanced.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

```powershell
python -X utf8 "<PLUGIN_ROOT>\analyze_enhanced.py" `
  --txt-path "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>" `
  --organized-output `
  --common-workflow `
  --context-query "评价当前小说片段的优缺点，给出具体、尖锐、可直接改章节的修改建议和后续剧情路线" `
  --context-max-items 160 `
  --context-excerpt-chars 1400
```

## 深度问答命令

当用户问的是具体文学判断，例如“某角色是否抛弃另一方”“后期身份是否等同”“结局选择是否合理”“冷战式不相认是否有铺垫”，优先使用 `answer_question.py`，不要只跑普通 `analyze_enhanced.py`。

小证据矩阵模式：

```powershell
python -X utf8 "<PLUGIN_ROOT>\answer_question.py" `
  --txt-path "<NOVEL_TXT>" `
  --question "<用户问题>" `
  --focus-entity "角色A" `
  --focus-entity "角色B" `
  --out-dir "<OUT_DIR>" `
  --organized-output
```

只有用户需要全文阅读、且已核对实际模型输入输出预算时，才启用大上下文阅读包。字符预算不等于 token 上限，不能按“1M”名称直接推定可容纳文本：

```powershell
python -X utf8 "<PLUGIN_ROOT>\answer_question.py" `
  --txt-path "<NOVEL_TXT>" `
  --question "<用户问题>" `
  --focus-entity "角色A" `
  --focus-entity "角色B" `
  --out-dir "<OUT_DIR>" `
  --organized-output `
  --large-context `
  --context-budget-chars 900000
```

以下比较命令仅用于用户明确要求的覆盖比较，不作为日常分析步骤：

```powershell
python -X utf8 "<PLUGIN_ROOT>\answer_question.py" `
  --txt-path "<NOVEL_TXT>" `
  --focus-entity "角色A" `
  --focus-entity "角色B" `
  --out-dir "<OUT_DIR>" `
  --organized-output `
  --compare-modes `
  --context-budget-chars 900000
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

分析完成后必须先检查任务文件夹根目录：

- `report.md`：用户真正要看的主报告或任务报告。
- `data/`：底座数据、证据包、提示词、缓存和调试文件。

`data/` 中必须检查这些文件：

- `llm_source_pack_detailed.md`
- `llm_source_pack_manifest.json`
- `review_evidence_pack.json`
- `editorial_revision_prompt.md`
- `entity_stats.json`
- `relation_triples.json`
- `sentiment_arc.json`
- `enhanced_briefs.json`

深度问答额外产物：

- `question_plan.json`
- `evidence_matrix.json`
- `coverage_audit.json`
- `reading_context_pack.md`
- `reading_context_manifest.json`
- `answer_prompt.md`
- `local_answer_report.md`

对比实验额外产物：

- `comparison_summary.json`
- `comparison_report.md`
- `llm_judge_prompt.md`

## 验收标准

- 任务根目录必须有 `report.md`，不要让用户自己进数据目录找主报告。
- `data/llm_source_pack_detailed.md` 必须包含 `[CHxxx-Pxxx]` 证据编号。
- `data/editorial_revision_prompt.md` 必须存在，后续深度报告优先使用它。
- 深度问答必须有 `data/evidence_matrix.json`；使用 1M 模式时 `data/reading_context_manifest.json` 中 `enabled` 应为 `true`。
- A/B 实验必须产出 `data/comparison_report.md`，并说明 `matrix_only` 与 `large_context` 的覆盖差异；根目录 `report.md` 是给用户看的摘要。
- 不要声称已生成 LLM 深度报告，除非实际运行了 `claudenovel-report` 或等效 `--llm-context-report`。

## 回复用户

只汇报核心结论、产物路径和下一步建议。不要把大段原文包或提示词全文贴进聊天。
