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
