# Claudenovel

Claudenovel 是一个面向中文长篇小说的分析、诊断和写作辅助工具。它会把小说文本解析成章节、场景、人物、关系、情绪曲线和质量指标，再生成带原文证据编号的分析材料，供作者、编辑或 LLM 继续做深度判断。

项目的核心原则是：重要结论必须能回到原文证据。证据编号形如 `[CH035-P001]`，表示第 35 章第 1 段。没有足够证据时，应明确标记为“证据不足”。

## 能做什么

- 解析中文小说 `.txt`，生成章节、场景、对白和段落索引。
- 统计人物出现频率、章节跨度和场景共现关系。
- 抽取人物关系三元组，辅助判断关系变化。
- 生成章节情绪曲线和基础质量指标。
- 构建带证据编号的 LLM 上下文包，减少空泛分析。
- 生成编辑诊断提示词，用于深度改稿、剧情路线和续写建议。
- 针对具体问题生成证据矩阵，例如“某角色是否抛弃另一方”“结局选择是否合理”。
- 支持单章改写、章节续写和独立的 agent 写作闭环。

## 适合场景

- 想快速了解一部长篇小说的人物、关系和情绪走势。
- 想让 LLM 基于原文证据做编辑诊断，而不是只给泛泛读后感。
- 想把大体量小说整理成可引用、可追溯的分析资料。
- 想围绕某条人物线、感情线或结局争议做证据化问答。
- 想搭建“章节合同 -> 生成 -> 审稿 -> 返修 -> 人工提交”的写作流程。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

把 UTF-8 编码的小说 `.txt` 放到项目根目录，然后运行：

```powershell
python analyze_enhanced.py
```

默认输出目录是 `novel_analysis_enhanced/`。

分析外部小说时，建议显式指定输入和输出目录：

```powershell
python analyze_enhanced.py `
  --txt-path "C:\path\to\novel.txt" `
  --out-dir "C:\path\to\output"
```

## 常用命令

生成证据化 LLM 上下文包：

```powershell
python analyze_enhanced.py `
  --build-context `
  --context-query "陈默和秦思妍的关系变化" `
  --focus-entity "陈默" `
  --focus-entity "秦思妍"
```

生成“原文整理 + 评价改进 + 后续剧情”的工作流产物：

```powershell
python analyze_enhanced.py `
  --common-workflow `
  --context-query "评价当前剧情并提出后续路线" `
  --source-start 1 `
  --source-end 20
```

调用已配置的 OpenAI-compatible 模型生成编辑报告：

```powershell
python analyze_enhanced.py `
  --llm-context-report `
  --context-prompt .\novel_analysis_enhanced\editorial_revision_prompt.md `
  --llm-output-name editorial_revision_report.md
```

单章质量评估：

```powershell
python analyze_enhanced.py --evaluate-chapter 1
python analyze_enhanced.py --evaluate-file .\my_chapter.txt
```

章节改写：

```powershell
python rewrite_chapter.py `
  --chapter-file "C:\path\to\chapter.txt" `
  --novel "C:\path\to\full_novel.txt" `
  --out-dir "rewritten"
```

从编辑报告中选择路线并续写：

```powershell
python continue_novel.py --report "report.md" --list
python continue_novel.py --report "report.md" --route 0 --novel "full.txt"
```

## 主要输出

常见输出文件包括：

- `entity_stats.json`：人物出现频率、章节跨度、场景共现。
- `relation_triples.json`：人物关系三元组。
- `sentiment_arc.json`：章节情绪走势。
- `enhanced_toc.md`：增强目录。
- `enhanced_briefs.json`：章节摘要索引。
- `evidence_pack.json`：带 `[CHxxx-Pxxx]` 编号的证据索引。
- `llm_context_prompt.md`：可交给 LLM 的证据化分析提示词。
- `llm_source_pack_detailed.md`：保留原文段落和证据编号的原文包。
- `editorial_revision_prompt.md`：用于生成深度编辑诊断报告的提示词。

如果启用整理后的输出布局，任务根目录通常会放面向用户阅读的 `report.md`，底层数据放在 `data/`。

## Agent 写作体系

`agent_writer/` 是一个独立的单章写作闭环，不是简单续写脚本。它围绕作者策略、读者期待、章节合同、角色边界、草稿生成、本地审稿、LLM 返修和人工确认提交运行。

最小示例：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo init --name "测试书" --genre "都市异能" --premise "主角调查旧楼铃声" --target-reader "男频都市读者"

python -X utf8 agent_writer_cli.py --project-root .agent-demo plan --chapter 1 --title "旧楼的第三声铃" --goal "主角进入旧楼确认铃声来源" --payoff "找到染血校牌" --ending-hook "校牌背面出现主角的名字" --character "秦思妍"

python -X utf8 agent_writer_cli.py --project-root .agent-demo generate --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo review --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo rewrite --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo commit --chapter 1 --approve
```

更完整的说明见 `AGENT_WRITER.md`。

## Agent 和插件支持

本仓库已经提供面向 Codex、Claude Code 和 Kimi CLI 的 skill/plugin 入口。自动化 agent 应优先读取这些文件，而不是把 README 当作执行手册：

- `CLAUDE.md`：仓库级 agent 协作规则、架构约束和常用命令。
- `skills/claudenovel-analyze/SKILL.md`：小说分析、证据包和深度问答。
- `skills/claudenovel-report/SKILL.md`：基于提示词生成编辑诊断报告。
- `skills/claudenovel-rewrite/SKILL.md`：单章审查和改写。
- `skills/claudenovel-continue/SKILL.md`：基于报告选择路线并续写。
- `plugins/Claudenovel/`：可安装的插件包。

README 只作为人类入口页；agent 的触发词、执行步骤和验收标准维护在 skill/plugin 文档中。`AGENTS.md` 可作为个人本地指令文件使用，但不作为仓库分发文档。

## 项目结构

- `novel_parser/`：核心解析、统计、检索、证据包和 LLM 上下文构建模块。
- `analyze_enhanced.py`：主分析入口。
- `answer_question.py`：针对具体文学判断的证据化问答入口。
- `rewrite_chapter.py`：章节改写入口。
- `continue_novel.py`：续写入口。
- `agent_writer/`：单章写作 agent 子系统。
- `skills/`：本仓库的 agent skill 定义。
- `plugins/Claudenovel/`：插件化后的可分发运行包。
- `webnovel-writer/`：并入的原 `webnovel-writer` 子项目，保留其原始结构和历史。

## 模型配置

项目读取 `.env` 或环境变量中的 OpenAI-compatible 配置。常用变量：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_KEY=你的 key
```

也支持 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 作为 fallback。

如果不配置模型，基础解析、统计、证据包和部分本地报告仍可运行；需要 LLM 的深度诊断、改写和续写不会自动完成。

## 更多文档

- `ARCHITECTURE.md`：模块结构和设计说明。
- `CLAUDE.md`：agent 工作规则。
- `AGENT_WRITER.md`：单章写作闭环说明。
- `DEEP_QUESTION_ANSWERING.md`：深度问答和 1M 上下文阅读包说明。
- `INSPIRATION_LIBRARY.md`：灵感库使用说明。
- `RETRIEVAL_BENCHMARK.md`：检索评测说明。

## 当前限制

- 小说输入推荐使用 UTF-8 `.txt`；`.docx` 需要先转换为 `.txt`。
- `--apply-aliases` 只适合仓库默认小说，外部小说通常不要启用。
- 证据抽取和关系识别主要依赖规则、统计和检索，不能替代人工编辑判断。
- LLM 输出质量取决于模型、上下文预算和提示词，不应在未运行验证时声称已生成最终报告。
