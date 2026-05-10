# 架构文档：feat/llm-vs-hybrid-compare 分支

> 本文档描述 `feat/llm-vs-hybrid-compare` 分支的完整文件架构、模块职责与数据流。

---

## 一、分支目标

验证并构建**混合架构（Hybrid）** for 长篇小说 LLM 分析：

- **本地结构化层**（`novel_parser`）：确定性提取人物、关系、情绪、质量指标
- **LLM 解读层**：基于结构化数据做深度分析，而非直接读全文
- **对比验证**：通过 `compare_approaches.py` 量化证明 Hybrid 优于纯 LLM
- **RAG + 记忆系统**：支持跨批次分析时携带前文上下文

---

## 二、目录结构

```
Claudenovel/
├── 入口脚本
│   ├── analyze_enhanced.py           # 主入口（增强分析流水线）
│   ├── analyze_novel.py              # 基础分析（legacy，保留兼容）
│   ├── analyze_qin_relationship.py   # 感情线专线分析
│   ├── compare_approaches.py         # 【核心】LLM vs Hybrid 对比实验
│   └── index_and_query_rag.py        # 【新增】NovelRAG 索引与查询 CLI
│
├── novel_parser/                     # 核心解析库（10 个模块）
│   ├── __init__.py
│   ├── normalizer.py                 # 编码检测、繁简转换、别名归一化
│   ├── structure.py                  # 卷/章/场景/对话结构解析
│   ├── entity.py                     # 人物统计、场景共现、说话人推断
│   ├── relation.py                   # 关系三元组（规则 + 可选 jieba POS）
│   ├── sentiment.py                  # 词典情绪弧线（正/负/紧张）
│   ├── evaluator.py                  # 章节质量评估（20+ 指标 vs 基准）
│   ├── llm_client.py                 # OpenAI/DeepSeek 兼容 LLM 客户端
│   ├── context_builder.py            # 证据化上下文包构建（段落级检索）
│   ├── common_workflows.py           # 常用工作流封装（原文包 + 评价提示词）
│   ├── pipeline.py                   # 完整流水线编排
│   ├── direct_llm_analyzer.py        # 【新增】纯 LLM 分析（对照组）
│   ├── hybrid_analyzer.py            # 【新增】混合架构分析（实验组）
│   └── memory_rag.py                 # 【新增】RAG + 记忆摘要系统
│
├── 输出目录
│   ├── novel_analysis/               # 基础分析输出（legacy）
│   ├── novel_analysis_enhanced/      # 增强分析输出
│   └── novel_analysis_comparison/    # 【新增】对比实验输出
│       ├── structured_baseline.json  # 结构化基准数据（全书 440 章）
│       ├── direct_results.json       # 纯 LLM 分析结果
│       ├── hybrid_results.json       # 混合分析结果
│       ├── comparison_report.md      # LLM 生成的对比报告
│       ├── cost_summary.json         # API 成本统计
│       └── comparison_prompt.md      # 对比提示词备份
│
├── 数据与配置
│   ├── apk.tw_地府微信群.txt         # 小说原文（UTF-8 简体中文）
│   ├── apk.tw_地府微信群.txt.bak     # 繁体原文备份
│   ├── .env                          # API Key 配置（不提交 Git）
│   ├── .gitignore
│   ├── requirements.txt
│   ├── README.md
│   ├── ARCHITECTURE.md               # 本文档
│   └── EXPERIMENT_REPORT.md          # 实验报告（LLM vs Hybrid 结果）
│
└── __pycache__/
```

---

## 三、模块职责详解

### 3.1 本地结构化层（Deterministic Layer）

| 模块 | 职责 | 输出 |
|------|------|------|
| `normalizer.py` | 编码自动检测、繁简转换、人物别名归一化（30+ 人） | 规范化文本 |
| `structure.py` | 正则提取卷/章，细分为段落 → 场景（地点关键词）→ 对话 | `List[Chapter]` |
| `entity.py` | 人物出场统计、章节跨度、场景级共现、说话人推断 | `entity_stats.json` |
| `relation.py` | 规则三元组（动词窗口）、可选 jieba POS 增强 | `relation_triples.json` |
| `sentiment.py` | 词典扫描情绪（正/负/紧张），逐章计算净值 | `sentiment_arc.json` |
| `evaluator.py` | 20+ 质量指标：冲突密度、对话比、TTR、悬念密度等 | 百分位评分 |

**核心原则**：零 API 成本、秒级运行、结果可复现、不丢失信息。

### 3.2 LLM 客户端层

| 模块 | 职责 |
|------|------|
| `llm_client.py` | OpenAI/DeepSeek 兼容 API 调用；支持编辑诊断、通用 chat、embedding |
| `context_builder.py` | 按查询目标筛选高信号段落，生成带编号 `[CH001-P003]` 的证据包 |
| `common_workflows.py` | 封装"原文整理 + 评价改进 + 后续剧情"完整工作流 |

### 3.3 对比实验层（新增）

| 模块 | 职责 |
|------|------|
| `direct_llm_analyzer.py` | **对照组**：直接送原文给 LLM，不附加任何结构化数据 |
| `hybrid_analyzer.py` | **实验组**：先跑结构化分析，再把统计结果 + 原文摘录送入 LLM |
| `compare_approaches.py` | 调度两种方法，收集结果，调用 LLM 写对比报告 |

**实验设计**：
- 控制变量：相同批次大小（5 章/批）、相同输出格式（JSON）、相同模型
- 差异变量：Direct 每章 8000 字原文 vs Hybrid 结构化数据 + 4000 字摘录
- 评估维度：人物识别、关系三元组、情感分析、API 成本、幻觉率

### 3.4 RAG + 记忆系统（新增）

| 模块 | 职责 |
|------|------|
| `memory_rag.py` | **NovelRAG**：Hybrid Retrieval（Dense + BM25 + RRF）+ 记忆摘要 |

**核心设计**：

```
┌─────────────────────────────────────────────────────────────┐
│  1. 场景级分块（SceneChunk）                                 │
│     - 按 structure.py 的 Scene 切分，保留叙事完整性           │
│     - Metadata：人物、地点、情绪、对话数、关系事件            │
├─────────────────────────────────────────────────────────────┤
│  2. 向量存储（SimpleVectorStore）                            │
│     - 纯 numpy cosine similarity，零依赖                      │
│     - Embedding：OpenAI text-embedding-3-small API            │
├─────────────────────────────────────────────────────────────┤
│  3. 稀疏检索（BM25Index）                                    │
│     - jieba 分词 + rank-bm25                                 │
├─────────────────────────────────────────────────────────────┤
│  4. 融合检索（HybridRetriever）                              │
│     - Metadata 预过滤（人物、章节范围、情绪阈值）             │
│     - Dense + Sparse 并行检索                                │
│     - RRF（Reciprocal Rank Fusion）合并排序                   │
├─────────────────────────────────────────────────────────────┤
│  5. 记忆摘要（MemorySummaryBuilder）                         │
│     - 从 structured_baseline 提取：人物弧光、关系里程碑       │
│     - 情绪关键点（峰谷检测）、质量趋势、未解钩子              │
│     - 支持跨批次累积（previous_memory → cumulative）          │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、数据流图

### 4.1 单次批次分析（1-10 万字）

```
小说原文 (.txt)
    ↓
[ normalizer + structure ] → Chapter 对象列表
    ↓
┌──────────────────────────────────────────┐
│  本地结构化层（并行执行）                  │
│  ├── entity.py → 人物统计                │
│  ├── relation.py → 关系三元组            │
│  ├── sentiment.py → 情绪弧线             │
│  └── evaluator.py → 质量指标             │
└──────────────────────────────────────────┘
    ↓
StructuredContext（JSON 证据包）
    ↓
┌──────────────────────────────────────────┐
│  LLM 深度层（单次调用）                    │
│  输入：证据包 + 筛选出的章节全文           │
│  任务：质量评价、对比前文、剧情建议        │
└──────────────────────────────────────────┘
    ↓
Markdown 报告 + MemorySummary
```

### 4.2 跨批次分析（携带前文记忆）

```
Batch N 分析完成后
    ↓
build_memory_summary(structured_baseline)
    → memory_summary.json（2KB 轻量摘要）
    ↓
Batch N+1 分析时
    → LLM 输入：memory_summary.json + Batch N+1 的 5 万字全文
    → 成本恒定，不随批次增长
```

### 4.3 RAG 查询流

```
用户查询："秦思妍情绪崩溃的章节"
    ↓
Metadata 过滤：sentiment_net < -3
    ↓
Dense 检索：embedding 相似度 Top-20
Sparse 检索：BM25 关键词匹配 Top-20
    ↓
RRF 融合 → Top-10 场景片段
    ↓
带证据编号的结果返回给用户/LLM
```

---

## 五、关键设计决策

### 5.1 为什么不用 ChromaDB / FAISS？

| 方案 | 问题 |
|------|------|
| ChromaDB | 依赖过重（grpc、kubernetes、onnxruntime），Windows 安装困难 |
| FAISS | 需要编译，Windows  wheel 不稳定 |
| **SimpleVectorStore** | 纯 numpy，100 行代码，性能对 440 章小说完全足够 |

### 5.2 为什么场景级分块优于固定长度？

- 场景是叙事的最小完整单元（同地点、同时间、同人物）
- 固定 1000 字切分会切断对话和动作描写
- 场景元数据（地点、人物、对话数）天然适合做 metadata 过滤

### 5.3 为什么 OpenAI Embedding API 而非本地模型？

- `text-embedding-3-small` 是目前中文语义检索的 SOTA 之一
- 避免引入 PyTorch（>2GB），保持项目轻量
- embedding 调用成本极低（~0.02 美元/100 万字）

---

## 六、使用示例

### 6.1 运行对比实验

```powershell
python compare_approaches.py --start 1 --end 50 --batch-size 5
```

输出：
- `novel_analysis_comparison/comparison_report.md` — LLM 写的对比报告
- `novel_analysis_comparison/cost_summary.json` — 成本统计

### 6.2 构建 RAG 索引

```powershell
# 需要配置 API Key
$env:OPENAI_API_KEY="sk-..."

python index_and_query_rag.py --index --start 1 --end 50
```

### 6.3 仅生成结构化记忆（零 API 成本）

```powershell
python index_and_query_rag.py --memory-only --start 1 --end 50
```

### 6.4 跨批次累积记忆

```powershell
# Batch 1: 1-50
python index_and_query_rag.py --memory-only --start 1 --end 50 --out-dir ./batch1

# Batch 2: 51-100，携带 Batch 1 记忆
python index_and_query_rag.py --memory-only --start 51 --end 100 `
  --memory-input ./batch1/memory_summary.json --out-dir ./batch2
```

---

## 七、文件变更记录（相对于 codex/evidence-grounded-context）

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `compare_approaches.py` | 新增 | LLM vs Hybrid 对比实验入口 |
| `index_and_query_rag.py` | 新增 | NovelRAG CLI |
| `novel_parser/direct_llm_analyzer.py` | 新增 | 纯 LLM 对照组 |
| `novel_parser/hybrid_analyzer.py` | 新增 | 混合架构实验组 |
| `novel_parser/memory_rag.py` | 新增 | RAG + 记忆摘要系统 |
| `novel_parser/llm_client.py` | 修改 | 增加 `call_direct_analysis`、`call_hybrid_analysis`、`call_chat` |
| `novel_parser/pipeline.py` | 修改 | 适配对比实验输出 |
| `novel_parser/normalizer.py` | 修改 | 繁简转换后的简体适配 |
| `novel_parser/structure.py` | 修改 | 简体场景标记 |
| `requirements.txt` | 修改 | 增加 numpy、rank-bm25 |
| `EXPERIMENT_REPORT.md` | 新增 | 50 章对比实验结果报告 |
| `ARCHITECTURE.md` | 新增 | 本文档 |

---

*分支：feat/llm-vs-hybrid-compare*
*最后更新：2026-04-28*
