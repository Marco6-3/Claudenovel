# kimi_lab 长篇小说分析工具

这个仓库用于对长篇小说文本做结构化解析、人物统计、关系抽取、章节质量评估，以及面向大上下文 LLM 的证据化提示词构建。

默认入口是 `analyze_enhanced.py`。脚本会自动读取当前目录下的 `.txt` 小说文件，并把结果写入 `novel_analysis_enhanced/`。

## 环境准备

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`jieba` 是可选增强依赖。不开启 `--use-jieba` 时，主流程仍可运行。

## 基础分析

```powershell
python analyze_enhanced.py
```

常见输出包括：

- `entity_stats.json`：人物出现频率、章节跨度、场景共现。
- `relation_triples.json`：人物关系三元组。
- `sentiment_arc.json`：章节情绪走势。
- `enhanced_toc.md`：增强目录。
- `enhanced_briefs.json`：章节摘要索引。

## 生成证据化 LLM 上下文包

如果要利用 DeepSeek 1M 上下文窗口，又尽量减少噪声，可以先生成带编号的证据包：

```powershell
python analyze_enhanced.py `
  --build-context `
  --context-query "陈默和秦思妍的关系变化" `
  --focus-entity "陈默" `
  --focus-entity "秦思妍" `
  --context-max-items 80 `
  --context-max-chars 80000
```

输出文件：

- `evidence_pack.json`：结构化证据索引，每条证据都有类似 `[CH054-P040]` 的稳定编号。
- `llm_context_prompt.md`：可直接复制给 LLM 的提示词，要求模型每个结论必须引用证据编号。

这个流程不是把全文无差别塞进上下文，而是先按查询目标和关注人物筛选高信号段落，再让 LLM 基于证据分析。

## Agent 调用指南：分析新小说片段并生成可改写报告

当另一个 agent 需要分析用户给的新小说或小说片段时，优先走这一节。目标不是生成泛泛读后感，而是生成**具体、尖锐、可直接改章节**的编辑诊断报告，供后续 `feat/chapter-rewriter` 读取和执行。

### 自然语言触发

如果用户用自然语言说：

- “帮我分析小说”
- “评价一下这个小说片段”
- “看看这几章写得怎么样”
- “给我后续剧情建议”
- “分析后让后续改写器能接着改”

agent 应默认执行完整分析闭环，而不是只给聊天建议：

1. 识别输入文件（`.txt` / `.docx`）。
2. 必要时把 `.docx` 转成 UTF-8 `.txt`。
3. 跑 `--common-workflow` 生成原文包、证据包、RAG/记忆资料和新版编辑诊断提示词。
4. 用 `editorial_revision_prompt.md` 调用 LLM 生成深度编辑报告。
5. 验收报告是否包含 P0/P1/P2、逐章改写清单和后续路线。
6. 最后只向用户报告核心结论和产物路径，不要把大段报告全文塞进聊天。

### 输入要求

- 推荐输入格式：UTF-8 `.txt`。
- 如果用户给的是 `.docx`，先转换成 `.txt`，再交给框架。不要直接把 `.docx` 路径传给 `--txt-path`。
- 外部小说必须显式传 `--txt-path`，不要依赖仓库默认 `.txt`。
- `--focus-entity` 应填写当前小说真实角色名；不知道角色名时可以先不填，或先运行基础分析后查看 `entity_stats.json`。

### 第一步：生成新版编辑诊断提示词

```powershell
python analyze_enhanced.py `
  --txt-path "C:\path\to\你的小说.txt" `
  --out-dir "C:\path\to\输出目录" `
  --common-workflow `
  --context-query "评价当前小说片段的优缺点，给出具体、尖锐、可直接改章节的修改建议和后续剧情路线" `
  --focus-entity "主角名" `
  --focus-entity "重要角色名" `
  --source-start 1 `
  --source-end 20 `
  --context-max-items 160 `
  --context-excerpt-chars 1400
```

如果是短篇或单个片段，`--source-end` 可以设为实际章节数；如果不确定章节数，可以先不填 `--source-start/--source-end`。

关键输出：

- `llm_source_pack_detailed.md`：保留原文段落和 `[CHxxx-Pxxx]` 证据编号。
- `review_evidence_pack.json`：筛选出的证据包。
- `editorial_revision_prompt.md`：新版深度编辑诊断提示词，优先使用这个文件。
- `entity_stats.json`、`relation_triples.json`、`sentiment_arc.json`、`enhanced_briefs.json`：人物、关系、情绪和章节索引资料，可作为 RAG/记忆材料。

### 可选：生成 RAG 索引和记忆摘要

如果用户提到“RAG”“资料库”“后续持续分析”“给别的 agent 用”，再运行：

```powershell
python index_and_query_rag.py `
  --txt-path "C:\path\to\你的小说.txt" `
  --out-dir "C:\path\to\输出目录" `
  --index
```

如果只是先生成轻量记忆摘要：

```powershell
python index_and_query_rag.py `
  --txt-path "C:\path\to\你的小说.txt" `
  --out-dir "C:\path\to\输出目录" `
  --memory-only
```

RAG/记忆相关输出通常包括 `memory_summary.json` 和向量/检索索引文件。后续 agent 应优先读取这些文件，而不是重新猜测前文。

### 第二步：调用 LLM 生成深度编辑报告

如果 `.env` 或环境变量已配置 DeepSeek / OpenAI 兼容接口，直接调用框架：

```powershell
python analyze_enhanced.py `
  --txt-path "C:\path\to\你的小说.txt" `
  --out-dir "C:\path\to\输出目录" `
  --llm-context-report `
  --context-prompt "C:\path\to\输出目录\editorial_revision_prompt.md" `
  --llm-output-name "editorial_revision_report.md"
```

合格报告应至少满足：

- 有 `必须修（P0）`、`建议增强（P1）`、`保留但控制（P2）`。
- 每个核心问题引用至少 2 个 `[CHxxx-Pxxx]` 证据编号。
- 有“逐章改写清单”，明确章节/段落、改写动作、目标字数变化、给改写器的指令。
- 有 5 条后续剧情路线，每条包含证据、风险、推荐写法和下一章钩子；短篇或单章也必须给满 5 条。
- 报告末尾不应附加 JSON 或结构化摘要；这份文件是给人读的深度分析和预测报告。

如果报告只有人物统计、情绪曲线和笼统建议，说明走错了旧流程；应改用 `editorial_revision_prompt.md` 重新调用 LLM。

## 常用工作流：原文整理 + 评价改进 + 后续剧情

如果目标是把原文整理成适合 LLM 深度分析的格式，并同时生成“评价、改进、后续剧情发展建议”的提示词，使用：

```powershell
python analyze_enhanced.py `
  --common-workflow `
  --context-query "评价陈默和秦思妍感情线的优缺点，并给出后续剧情发展建议" `
  --focus-entity "陈默" `
  --focus-entity "秦思妍" `
  --source-start 1 `
  --source-end 20
```

常用输出：

- `llm_source_pack_detailed.md`：具体版原文输入包，保留章节、段落和原文内容，并给每段生成 `[CH001-P003]` 这类引用编号。
- `llm_source_pack_manifest.json`：原文输入包索引，便于确认包含了哪些章节和段落。
- `review_evidence_pack.json`：按问题和关注人物筛出来的证据包。
- `review_improve_continue_prompt.md`：可直接交给 LLM 的提示词，要求输出总体评价、优点、问题、可执行改进和 3 条后续剧情路线。

如果要限制输入包体积，可以加 `--source-max-chars`。例如只允许约 20 万字符：

```powershell
python analyze_enhanced.py `
  --common-workflow `
  --context-query "评价当前剧情并提出后续路线" `
  --source-start 1 `
  --source-end 80 `
  --source-max-chars 200000
```

这个“具体版”不会把章节改写成简化摘要；预算不足时只会减少纳入的章节，并在输出里标记截断。

如果已经配置了 DeepSeek / OpenAI 兼容接口，可以直接让模型读取上面的提示词生成报告：

```powershell
python analyze_enhanced.py `
  --llm-context-report `
  --context-prompt .\novel_analysis_enhanced\review_improve_continue_prompt.md `
  --llm-output-name review_improve_continue_report.md
```

## 章节质量评估

评估原书中的某一章：

```powershell
python analyze_enhanced.py --evaluate-chapter 1
```

评估外部输入章节：

```powershell
python analyze_enhanced.py --evaluate-file .\my_chapter.txt
```

如果配置了 OpenAI 兼容接口，也可以生成 LLM 编辑诊断：

```powershell
$env:OPENAI_API_KEY="你的 key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"

python analyze_enhanced.py --evaluate-file .\my_chapter.txt --llm-report
```

## 设计原则

- 每个分析结论尽量绑定原文证据编号。
- 没有证据时明确标记“证据不足”。
- 先抽取证据，再做推断，避免空泛总结。
- 大上下文窗口优先放高密度证据、人物索引和任务规则，而不是无差别全文。
