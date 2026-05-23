# 检索证据底座验收与收敛方案

本文件定义 Claudenovel 的长篇网文证据检索验收标准。目标不是判断 LLM 写得好不好，而是在 LLM 分析前先判断：证据包是否覆盖了关键剧情、是否足够精确、是否能在可接受时间内生成。

## 样例任务

当前内置样例为《都市之修仙归来》的“楚云 / 萧雨琪 / 琪皇”全书感情线。

这个样例刻意覆盖长篇分析中最容易漏的几类情节：

- 开局重生、前世遗憾、婚约承诺。
- 中段等待、望云湖、逆天赴约。
- 蕴龙骨、寿元危机、婚礼和反转。
- 妻子、母亲、孩子、楚凡等家庭身份。
- 琪皇转世、三皇责任、身份撕裂。
- 离开、冷战、不相认、跪首、献祭、和解。

## 验收标准

每个算法必须在内置 gold cases 上评测：

- `must_recall`：关键章节必须召回，平均值目标 `>= 0.85`。
- `expected_recall`：阶段相关章节召回，平均值目标 `>= 0.55`。
- `precision`：返回章节中相关章节比例，平均值目标 `>= 0.16`。
- `pass_rate`：通过用例比例，目标 `>= 0.80`。
- `latency_ms`：在满足质量底线后越低越好。

注意：分用例 precision 门槛会按 gold 章节数和 `top_k` 自动封顶。原因是某些用例只有 4 个 gold 章节，若 `top_k=24`，理论最高 precision 也只有 `4/24=0.167`，不能用固定 `0.20` 作为硬门槛。

最终收敛算法不只看召回率，而是综合：

- 关键章节召回。
- 阶段覆盖。
- 精确率。
- 分用例通过率。
- 查询效率。

## 当前待比较算法

- `keyword`：关键词和角色称谓加权，速度快，适合强人名/强道具问题。
- `bm25`：jieba + BM25，适合原文词面明确的问题。
- `ngram`：字符 n-gram 轻量近似，作为无外部 embedding 的语义兜底。
- `embedding`：本地 TF-IDF/哈希向量余弦检索，默认离线可复现；也预留 `--embedding-mode api`。
- `hybrid_rrf`：keyword + BM25 + n-gram 的 RRF 融合。
- `embedding_hybrid_rrf`：embedding + keyword + BM25 + n-gram 的通用混合底座。
- `adaptive_evidence_base`：在通用混合底座上增加边界锚点和时间线覆盖，避免全书问题只召回中段高频章节。
- `multi_probe_hybrid`：把问题拆成多个低频高信号词探针分别检索，目前作为实验对照，不作为默认推荐。
- `chronological_hybrid`：在混合检索上加入时间线多样性，避免证据全挤在一个阶段。
- `relationship_template`：人物感情线专题模板，强制覆盖起点、相思、危机、家庭、身份、分离、回收等阶段。
- `relationship_template_fast`：人物感情线快速模板，用阶段锚点 + BM25 回填降低耗时，用来验证能否替代完整模板。

## 当前收敛结论

在《都市之修仙归来》楚云 / 萧雨琪 / 琪皇样例上，`top_k=24`、`workers=6` 的实测结论是：

| 算法 | Pass Rate | Must Recall | Expected Recall | Precision | Avg Latency | 结论 |
|---|---:|---:|---:|---:|---:|---|
| `relationship_template` | 1.00 | 1.00 | 0.83 | 0.27 | 2827.0 ms | 通过验收，专题分析收敛算法 |
| `relationship_template_fast` | 0.71 | 0.93 | 0.70 | 0.23 | 1123.4 ms | 更快，但未过 `pass_rate >= 0.80` |
| `embedding_hybrid_rrf` | 0.43 | 0.79 | 0.68 | 0.21 | 2864.7 ms | 当前最好的通用底座 |
| `adaptive_evidence_base` | 0.43 | 0.79 | 0.68 | 0.21 | 3127.0 ms | 质量接近，但更慢 |
| `hybrid_rrf` | 0.29 | 0.71 | 0.67 | 0.19 | 2475.4 ms | 无 embedding 的通用融合 |
| `chronological_hybrid` | 0.29 | 0.74 | 0.63 | 0.18 | 2455.1 ms | 时间线更均衡，但召回不足 |
| `keyword` | 0.14 | 0.74 | 0.59 | 0.18 | 330.8 ms | 快，但漏关键情节 |
| `ngram` | 0.29 | 0.64 | 0.55 | 0.16 | 1033.5 ms | 可兜底，不能单独承担长线分析 |
| `bm25` | 0.29 | 0.64 | 0.53 | 0.16 | 1104.5 ms | 词面依赖强 |
| `multi_probe_hybrid` | 0.14 | 0.57 | 0.39 | 0.22 | 5821.2 ms | 当前实验失败，不推荐 |
| `embedding` | 0.00 | 0.60 | 0.35 | 0.10 | 138.1 ms | 纯向量召回不足 |

因此当前结论分两层：

- **通用底座**：优先使用 `embedding_hybrid_rrf`，它比无 embedding 的 `hybrid_rrf` 有更高 must recall、expected recall 和 precision。
- **专题深分析**：人物感情线仍必须叠加 `relationship_template` 这类专题模板；在本样例上，唯一全量过线的是 `relationship_template`。

本地 embedding 首次构建约 `18.5s`，会在输出目录写入 `embedding_cache_local_d2048.npz`。同一输出目录第二次运行会复用缓存，本次实测 embedding 构建耗时降到约 `238ms`。

## 运行命令

```powershell
python .\benchmark_retrieval.py `
  --txt-path "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt" `
  --out-dir "C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\claudenovel_chuyun_xiaoyuqi\retrieval_benchmark" `
  --top-k 24 `
  --workers 6
```

可选参数：

```powershell
# 默认：本地离线 embedding
--embedding-mode local

# 可选：外部 OpenAI-compatible embedding API，不作为默认，避免批量索引时被接口和费用卡住
--embedding-mode api

# 关闭 embedding，只跑传统稀疏/规则算法
--embedding-mode off
```

输出：

- `retrieval_benchmark_report.json`：机器可读指标。
- `retrieval_benchmark_report.md`：人工评审报告。

## 使用原则

标准证据底座只解决“不要漏关键证据”的下限。对于人物感情线、伏笔回收、剧情合理性、角色争议等专题问题，应在通用检索之上叠加专题模板。

如果某个专题模板比通用算法明显更好，后续应把它固化为 `analyze_arc.py --topic <topic>` 的标准入口，而不是每次临时手写提示词。
