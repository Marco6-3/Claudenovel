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
