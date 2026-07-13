# Branch-first + Adaptive Expand 可行性实验

这个实验只作用于 benchmark 运行目录，不接入 `agent_writer/` 生产流水线。

流程：

1. 三个互相隔离的 Planner 只生成结构化 Branch Card，不写正文。
2. Root 检查 IdeaContract、禁改项和宏观事件重合；重合过高时只返工冲突分支。
3. 先扩写两条合同合格且最互补的分支。
4. 对两篇正文做成对、正反顺序盲评；一致则停止，不一致才扩写第三条。
5. 最终候选与 direct-best 基线另做盲比，自动 Judge 不代替人类偏好。

构造 Planner 提示词：

```bash
python -X utf8 experiments/branch_first_v1/prepare_branch_prompts.py \
  --public-run /path/to/public-benchmark-run \
  --out-dir /path/to/branch-first-run \
  --case after_chapter_11 \
  --case after_chapter_16
```

Writer、Planner 和独立 Judge 都不得读取 benchmark private 目录、目标原章、其他 Planner 的卡片或匿名映射。

## 已归档试运行

`runs/pilot_2026-07-13/` 保存第 11、16 章后两个切点的完整实验链：Planner prompt、Branch Card、选择 prompt、匿名映射、原始判断、扩写正文、交换顺序正文评审、与 Direct-best 的对比评审及报告。它依赖：

```text
experiments/difu_early_continuation_v1/runs/pilot_2026-07-13/
```

下一次 clone 后可先重跑结构校验：

```bash
python -X utf8 experiments/branch_first_v1/validate_branch_cards.py \
  --run-dir experiments/branch_first_v1/runs/pilot_2026-07-13 \
  --public-run experiments/difu_early_continuation_v1/runs/pilot_2026-07-13 \
  --case after_chapter_11 \
  --case after_chapter_16
```

两个切点的聚合结果已经随 run bundle 保存。下一轮应沿用同一目录契约，继续 `after_chapter_1`、`after_chapter_4`、`after_chapter_22` 和 `after_chapter_26`，并先加入六轴事件指纹门和“先独评、后比较”的 Judge 协议。
