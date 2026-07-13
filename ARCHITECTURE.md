# Claudenovel 架构

## 产品边界

默认生成能力只处理一个独立叙事单元：单章、短篇或单元剧一集。外部创意是唯一写作真源；跨卷规划、历史摘要回灌、长期关系/伏笔账本和无人值守续章不在默认生成链中。

`novel_parser/` 保留为只读分析底座，供作者理解现有材料、寻找证据或诊断指定单章。分析结果只有在作者显式写入 `IdeaContract` 后，才能成为生成约束。

## 写作数据流

```text
human/external source_text
  → IdeaContract
      ├── idea_locks
      ├── forbidden_changes
      ├── freedom_budget
      └── success_criteria
  → UnitContract + CharacterConstraints + PrewritePlan
  → Candidate Writers (homogeneous or diverse)
  → deterministic local gate
  → Judge pass 1 (forward order)
  → Judge pass 2 (reversed order)
  → consistent winner only
  → review hashes
  → explicit human approval
  → accepted unit + commit audit
```

## 模块

| 模块 | 责任 | 明确不做 |
|---|---|---|
| `agent_writer/models.py` | 外部创意、单元、角色、审稿和提交契约 | 跨卷状态模型 |
| `agent_writer/pipeline.py` | 计划、生成、候选选优、返修和提交 | 读取前章或自动续章 |
| `agent_writer/quality_gate.py` | 创意锁、禁改项、payoff、角色和系统硬闸 | 用本地规则声称理解所有语义 |
| `agent_writer/index_store.py` | 产物、问题和提交审计 | 保存叙事记忆 |
| `novel_parser/` | 对用户指定材料做证据化分析 | 自动把分析建议变成正文 |
| `experiments/single_unit_v1/` | 对照条件、任务集和评价协议 | 产品运行时状态 |

## 真源优先级

1. `IdeaContract.source_text` 与创意锁。
2. 人类明确给出的禁改项、自由预算和成功标准。
3. 当前单元合同与角色边界。
4. 项目级作者策略和规则包。
5. Writer 或 Judge 的自由判断。

低优先级信息不得覆盖高优先级信息。已接受旧章节也不会自动覆盖当前外部创意。

## 评审边界

本地硬闸负责可确定检查，Judge 负责需要语义判断的六维评分：创意忠实度、单元弧、人物因果、场景与语言、情绪兑现、原创性。Judge 看不到条件名和模型名，并以相反候选顺序运行两次；胜者不一致时结果为不确定。

最终质量结论仍需人类抽样复评。自动 Judge 是筛选器与测量工具，不是作者所有权的替代品。

## 持久化

写作项目只保存当前单元的合同、提示词、候选、审稿、接受稿和审计事件。SQLite 位于 `.agent_writer/index.db`，没有长期人物关系、伏笔或章节摘要表。
