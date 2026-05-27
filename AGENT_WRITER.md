# Agent Writer 体系说明

`agent_writer/` 是 Claudenovel 内的独立写作 agent 子系统，落点是“单章极致质量闭环”，不是通用补文器。

## 设计边界

- 生成前必须有 `writer_strategy`、`reader_expectation_map`、`chapter_contract`、`character_constraints`、`prewrite_plan`。
- 隐藏/未来章节不得进入生成或返修 prompt，只能用于事后评估。
- 审稿出现 blocking 时不得提交。
- `rewrite` 只服务于修复审稿问题、表达压缩和风格校准，不替代章节合同。
- `commit --approve` 是人工门控，只有通过审稿后才写入 `accepted/`、`commits/` 和 `state/`。

## 调研资产映射

规则包位于 `agent_writer/rules/`：

| 文件 | 来源 | 用途 |
|---|---|---|
| `character_boundary.json` | `novel-research/novle1/05` | 角色阶段、允许行为、禁止行为、OOC 红线 |
| `chapter_commercial_function.json` | `novel-research/novle1/06` | 爽点、期待、冲突升级、尾钩 |
| `module_protocol.json` | `novel-research/novle1/09` | 八层模块输入输出与检查项 |
| `workflow.json` | `novel-research/novle1/10` | 章纲先行、审稿必做、中间产物持久化、人工门控 |

这些规则会进入 `prompts/chapter_XXXX_writer_prompt.md`，同时本地质量门禁会执行其中的硬阻断项。

## CLI

```powershell
python -X utf8 agent_writer_cli.py --project-root <书项目目录> <command>
```

命令：

- `init`：初始化书项目真值层。
- `plan`：生成章节合同、角色边界卡和 prewrite plan。
- `write`：生成写作任务书，或导入外部草稿。
- `generate`：调用 LLM 生成草稿。
- `review`：运行本地质量门禁。
- `rewrite-brief`：生成文件化返修 brief。
- `rewrite`：调用 LLM 按返修 brief 重写。
- `commit --approve`：人工确认后提交章节。
- `status`：查看计数状态。
- `index-report`：查看 SQLite 索引中的产物和 blocking issues。
- `llm-smoke`：验证 LLM 配置可用。
- `discuss`：生成作者协商包。
- `draft-author-note`：从分析产物生成决策候选。
- `record-author-note`：从 JSON 文件记录作者确认决策。
- `handoff`：生成章节交接包。
- `plan-next`：基于交接 + 作者决策规划下一章。
- `experiment`：运行 A/B/C/D 记忆变体实验。
- `evaluate-workflow`：评估作者记忆工作流完整性（证据传播、禁区检查等）。
- `compare-memory-variants`：比较不同记忆变体（baseline/handoff/author_memory/full）的约束、证据、伏笔差异。

## 作者记忆系统

每章提交后，作者可以通过协商包确认决策，系统自动沉淀到长期状态：

```powershell
# 1. 生成作者协商包
python -X utf8 agent_writer_cli.py discuss --chapter 1

# 2.（可选）从分析产物生成决策候选
python -X utf8 agent_writer_cli.py draft-author-note --chapter 1 --analysis-dir .\novel_analysis_enhanced\

# 3. 作者确认决策（从 JSON 文件读取）
python -X utf8 agent_writer_cli.py record-author-note --chapter 1 --decision-file decision.json

# 4. 生成交接包
python -X utf8 agent_writer_cli.py handoff --chapter 1

# 5. 规划下一章（自动加载交接 + 作者决策）
python -X utf8 agent_writer_cli.py plan-next --chapter 2 --title "档案室的空座" --goal "追查校牌" --payoff "发现空座名单" --ending-hook "名单被改写"
```

### 分析产物 → 作者决策候选 桥接

`draft-author-note` 从分析系统输出目录读取以下文件（全部可选，缺失时降级）：

| 文件 | 用途 |
|---|---|
| `evidence_pack.json` | 评分后的证据段落，带 `[CHxxx-Pxxx]` ID |
| `editorial_revision_prompt.md` | 编辑诊断报告，含 P0 问题和续写路线 |
| `evidence_matrix.json` | QA 证据矩阵（带立场标注） |
| `review_evidence_pack.json` | 审稿专用证据包 |
| `llm_source_pack_manifest.json` | 章节/段落索引清单 |

生成的候选文件位于 `author_discussion/`：
- `chapter_XXXX_decision_candidate.json`：结构化候选（DecisionCandidate 模型）
- `chapter_XXXX_decision_candidate.md`：可读候选报告

**重要**：候选文件不会直接写入 `state/`。只有通过 `record-author-note` 确认后，决策才会进入长期状态。

候选内容包含：
- 建议保留的内容（附证据 ID）
- 建议修改的问题（P0 问题，附证据 ID）
- 下一章发展方向候选（从续写路线提取）
- 活跃伏笔 / 可回收伏笔候选
- 角色 / 关系状态变化候选
- 作者禁区候选

### 证据溯源

确认后的作者决策携带 `evidence_refs`（如 `[CH001-P003]`），这些证据 ID 会：
- 进入交接包的 `hard_constraint_evidence` 和 `author_direction_evidence`
- 写入下一章合同的 `allowed_sources` 或 `foreshadowing_ops`
- 使作者和模型都能看到关键约束的证据来源

### 证据覆盖门禁

评估工作流包含证据覆盖检查：
- 分析来源（`source=analysis_derived`）的方向无 `evidence_refs` → risk
- 作者原创（`source=author_confirmed`）的方向不要求证据
- 交接包中的证据未在合同/prompt 中引用 → risk

## 可复现 Smoke 工作流

以下命令序列可验证完整作者记忆工作流，不调用真实 LLM：

```powershell
# 1. 初始化项目
python -X utf8 agent_writer_cli.py init --name "测试书" --genre "都市异能" --premise "校园灵异" --target-reader "悬疑读者"

# 2. 规划第1章
python -X utf8 agent_writer_cli.py plan --chapter 1 --title "旧楼的第三声铃" --goal "确认铃声来源" --payoff "找到染血校牌" --ending-hook "校牌背面出现主角的名字"

# 3. 导入草稿（或用 generate 调 LLM）
# 手动写一个 draft.md，然后:
python -X utf8 agent_writer_cli.py write --chapter 1 --draft-file draft.md

# 4. 审稿
python -X utf8 agent_writer_cli.py review --chapter 1

# 5. 提交
python -X utf8 agent_writer_cli.py commit --chapter 1 --approve

# 6. 从分析产物生成决策候选
python -X utf8 agent_writer_cli.py draft-author-note --chapter 1 --analysis-dir .\novel_analysis_enhanced\

# 7. 生成作者协商包
python -X utf8 agent_writer_cli.py discuss --chapter 1

# 8. 作者确认决策
python -X utf8 agent_writer_cli.py record-author-note --chapter 1 --decision-file decision.json

# 9. 生成交接包
python -X utf8 agent_writer_cli.py handoff --chapter 1

# 10. 规划下一章
python -X utf8 agent_writer_cli.py plan-next --chapter 2 --title "档案室的空座" --goal "追查校牌" --payoff "发现空座名单" --ending-hook "名单被改写"

# 11. 评估工作流
python -X utf8 agent_writer_cli.py evaluate-workflow --chapter 1

# 12. 比较记忆变体
python -X utf8 agent_writer_cli.py compare-memory-variants --chapter 1
```

也可以通过 pytest 运行完整 smoke 测试：

```powershell
python -X utf8 -m pytest tests/test_agent_writer_pipeline.py::test_full_author_memory_smoke_no_llm -v
```

## 推荐日常使用顺序

每章完整闭环：

1. `plan` — 规划章节合同
2. `write` 或 `generate` — 导入草稿或调 LLM 生成
3. `review` — 质量门禁
4. `commit --approve` — 人工确认提交
5. `draft-author-note` — 从分析产物生成决策候选
6. `discuss` — 生成作者协商包（已嵌入候选）
7. `record-author-note` — 作者确认决策
8. `handoff` — 生成交接包
9. `plan-next` — 规划下一章（自动加载交接 + 决策）
10. `evaluate-workflow` — 验证工作流完整性
11. `compare-memory-variants` — 比较记忆增量

评估/诊断命令（随时可用）：
- `evaluate-workflow`：检查证据传播、禁区检查、payoff 兑现
- `compare-memory-variants`：查看各记忆层级带来的约束差异
- `status`：查看项目整体进度
- `index-report`：查看 SQLite 索引和 blocking issues
- `python scripts/check_plugin_drift.py`：检查插件文档漂移

## 状态与索引

每个书项目会生成：

- `story_bible/writer_strategy.json`
- `expectations/reader_expectation_map.json`
- `chapter_contracts/chapter_XXXX_contract.json`
- `chapter_contracts/chapter_XXXX_character_constraints.json`
- `chapter_contracts/chapter_XXXX_prewrite_plan.json`
- `prompts/chapter_XXXX_writer_prompt.md`
- `drafts/chapter_XXXX_draft.md`
- `reviews/chapter_XXXX_review.json`
- `accepted/chapter_XXXX.md`
- `commits/chapter_XXXX_commit.json`
- `author_discussion/chapter_XXXX_packet.md`：作者协商包
- `author_discussion/chapter_XXXX_decision_candidate.json`：分析生成的决策候选
- `author_discussion/chapter_XXXX_decision_candidate.md`：决策候选可读版
- `handoffs/chapter_XXXX_handoff.json`：章节交接包（JSON）
- `handoffs/chapter_XXXX_handoff.md`：交接包可读版
- `evaluations/workflow_evaluation_chapter_XXXX.json`：工作流评估结果
- `evaluations/workflow_evaluation_chapter_XXXX.md`：工作流评估可读版
- `experiments/memory_variant_comparison_chapter_XXXX.json`：记忆变体比较
- `experiments/memory_variant_comparison_chapter_XXXX.md`：记忆变体比较可读版
- `state/agent_writer.db`
- `state/author_decisions.json`：已确认的作者决策
- `state/future_direction_ledger.json`：未来方向账本
- `state/foreshadowing_ledger.json`：伏笔账本（只增不删）
- `state/relationship_state.json`：角色关系状态
- `state/chapter_summaries.json`：章节摘要
- `state/characters.json`：角色档案
- `state/system_rule_ledger.json`：系统规则变更

SQLite 表：

- `chapter_artifacts`：记录 contract、prompt、draft、review、rewrite、commit 路径。
- `review_issues`：记录结构化审稿问题。
- `state_events`：记录人工确认后的提交事件。
