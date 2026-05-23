# Codex 深度问答工作流

本工作流用于回答“人物是否抛弃”“身份是否等同”“结局是否合理”“冷战式不相认是否有铺垫”等细致问题。它不是单纯 RAG，也不是让 LLM 自由发挥，而是先拆题、检索、审计证据，再生成受控提示词。

## 能力边界

- `benchmark_retrieval.py` 用来评测检索算法是否漏关键证据。
- `answer_question.py` 用来处理一个具体问题，并输出拆题、证据矩阵、覆盖审计和回答提示词。
- `answer_question.py --large-context` 用来启用 1M 上下文友好的“大阅读包”模式，让 LLM 先读全书范围的可引用材料，再回答细问题。
- `answer_question.py --compare-modes` 用来做 A/B 实验，比较当前小证据矩阵模式和 1M 大上下文模式。
- 默认不调用外部 LLM，保证离线可跑；加 `--llm` 后才调用 `.env` 中配置的 OpenAI-compatible 模型。

## 运行示例

```powershell
python .\answer_question.py `
  --txt-path "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt" `
  --question "萧雨琪是否抛弃了楚云和楚凡？" `
  --focus-entity "楚云" `
  --focus-entity "萧雨琪" `
  --out-dir "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\claudenovel_chuyun_xiaoyuqi\deep_qa\abandonment"
```

如果通过 skill 使用，默认加上 `--organized-output`，输出结构会变成：

- `<OUT_DIR>\report.md`：用户直接阅读的指定问题报告。
- `<OUT_DIR>\data\`：证据矩阵、阅读包、提示词、缓存和其他底座数据。

调用 LLM 生成最终自然语言分析：

```powershell
python .\answer_question.py `
  --txt-path "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt" `
  --question "最后萧雨琪没有跟楚云走是否合理？" `
  --focus-entity "楚云" `
  --focus-entity "萧雨琪" `
  --out-dir "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\claudenovel_chuyun_xiaoyuqi\deep_qa\ending_rationality" `
  --organized-output `
  --llm
```

启用 1M 大上下文模式：

```powershell
python .\answer_question.py `
  --txt-path "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt" `
  --question "萧雨琪是否抛弃了楚云和楚凡？" `
  --focus-entity "楚云" `
  --focus-entity "萧雨琪" `
  --out-dir "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\claudenovel_chuyun_xiaoyuqi\deep_qa\abandonment_large" `
  --organized-output `
  --large-context `
  --context-budget-chars 900000
```

比较小矩阵模式和 1M 大上下文模式：

```powershell
python .\answer_question.py `
  --txt-path "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt" `
  --focus-entity "楚云" `
  --focus-entity "萧雨琪" `
  --out-dir "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\claudenovel_chuyun_xiaoyuqi\deep_qa\compare_modes" `
  --organized-output `
  --compare-modes `
  --context-budget-chars 900000
```

## 输出文件

- `question_plan.json`：问题分类、关注对象、子问题拆解和使用算法。
- `evidence_matrix.json`：证据矩阵，证据 ID 形如 `[CH001-P001]`。
- `coverage_audit.json`：早期/中期/后期/结局覆盖、支持/反方证据状态、补检索记录。
- `reading_context_pack.md`：大上下文阅读包；未启用 `--large-context` 时只记录未启用状态。
- `reading_context_manifest.json`：阅读包覆盖统计，包括时间段、关系阶段、章节数和字符预算。
- `reading_context_records.json`：阅读包的结构化证据记录。
- `answer_prompt.md`：交给 LLM 的受控提示词，固定要求引用证据。
- `local_answer_report.md`：离线本地报告，便于 Codex 或人工继续分析。
- `llm_answer_report.md`：仅在使用 `--llm` 时生成。

`--compare-modes` 额外输出：

- `comparison_summary.json`：两种模式的离线指标。
- `comparison_report.md`：A/B 实验报告。
- `llm_judge_prompt.md`：可交给 LLM 或人工评审的 A/B 成文质量评审提示词。

## 当前策略

- 通用底座默认使用 `embedding_hybrid_rrf`。
- 人物感情线、身份、角色争议、结局合理性和冷战问题会自动叠加 `relationship_template`。
- 覆盖审计会检查早期、中期、后期、结局，以及支持证据和反方证据。
- 缺时间段证据时会自动做一次直接补检索。
- 大上下文模式会从全书扫描与问题、人物、关系阶段相关的段落，生成可引用的“读完整本后的材料包”。
- LLM 回答时先使用 `reading_context_pack.md` 建立全书印象，再使用 `evidence_matrix.json` 作为高置信锚点校准关键判断。

## A/B 实验标准

默认比较四个验收问题，每题同时跑：

- `matrix_only`：当前证据矩阵模式，优点是短、便宜、稳定，缺点是可能缺少全书感情线印象。
- `large_context`：1M 大上下文模式，优点是覆盖更接近“读完整本后评论”，缺点是提示词更长、成本更高。

离线评分会检查：

- 早期、中期、后期、结局是否覆盖。
- 感情线阶段是否覆盖：开端、等待、危机、家庭、身份、分离、回收。
- 子问题是否都有证据。
- 是否同时有支持证据和反方证据。
- 提示词大小是否仍适合 1M 上下文。

如配置 `--llm`，两种模式都会生成自己的 `llm_answer_report.md`，再用 `llm_judge_prompt.md` 做人工或 LLM 评审。

## 验收问题

首批用《都市之修仙归来》楚云 / 萧雨琪线验证：

- “琪皇是否就是萧雨琪？”
- “萧雨琪是否抛弃了楚云和楚凡？”
- “最后萧雨琪没有跟楚云走是否合理？”
- “两人冷战式不相认是否有前文铺垫？”

合格回答必须引用证据 ID，必须同时讨论支持证据和反方证据，必须说明证据缺口。
