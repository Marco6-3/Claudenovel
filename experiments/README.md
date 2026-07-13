# Claudenovel 实验索引与继续运行顺序

本目录同时保存实验协议、可执行工具和不可变的历史 run bundle。新 clone 不需要依赖此前机器上的 `outputs/` 或 `work/`，即可检查已经得到的证据并继续下一轮。

## 0. 环境与基线验证

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -o addopts='' -q
```

不要把 `.env`、SQLite、虚拟环境、缓存或供应商凭据放入 `runs/`。

## 1. 外部创意优先的通用单元实验

入口：`single_unit_v1/`

- `tasks.json`：六类外部创意任务。
- `rubric.json`：以创意忠实度为最高权重的评价树。
- `manifest.json`：C0–C5 条件定义。
- `runs/external_idea_mini_2026-07-13/`：三个隔离 Writer 的第一次真实小实验，包括 IdeaContract、三篇候选、正反序 Judge 原始结果、聚合报告。

这一阶段证明：创意锁可以约束多个 Writer，但单一 Judge 有明显位置敏感性；胜者不一致时必须输出 `judge_uncertain`。

## 2. 《地府微信群》Direct-best 基线

入口：`difu_early_continuation_v1/`

`runs/pilot_2026-07-13/` 保存第 11、16 章后两个无泄漏断点的完整基线证据：

- 公开 IdeaContract 和 Writer 实际 prompt；
- 每个断点三篇正文候选；
- 正反序匿名映射和 Judge 原始 JSON；
- 独立质量、作者路线贴合度聚合结果；
- 完整试运行报告。

重跑离线架构诊断：

```bash
python -X utf8 experiments/difu_early_continuation_v1/analysis/analyze_pilot.py
```

结果应与 `analysis/pilot_analysis_result.json` 一致。人工宏观事件标签在 `analysis/semantic_features.json`，只用于探索性分析，不是真值标注。

## 3. 论文调研与架构收敛

按阅读顺序：

1. `docs/research/single-unit-writing-experiments.md`：通用实验协议与论文依据。
2. `docs/research/ARCHITECTURE_RESEARCH.md`：利用 Direct-best 试运行做离线架构探针，收敛到 Branch-first。
3. `docs/research/BROAD_ARCHITECTURE_RADAR.md`：更广的架构族、反证和后续研究菜单。

这些报告是研究结论，不是生产默认行为。

## 4. Branch-first + Adaptive Expand

入口：`branch_first_v1/`

`runs/pilot_2026-07-13/` 完整保存：

- 三类 Planner 的实际 prompt 和 Branch Card；
- 合同门、多样性复核与选卡结果；
- 两条入围分支的正文；
- 正反序正文评审；
- 与 Direct-best 的对照评审；
- 匿名映射、原始判断、聚合结果和完整报告。

先验证归档卡片：

```bash
python -X utf8 experiments/branch_first_v1/validate_branch_cards.py \
  --run-dir experiments/branch_first_v1/runs/pilot_2026-07-13 \
  --public-run experiments/difu_early_continuation_v1/runs/pilot_2026-07-13 \
  --case after_chapter_11 \
  --case after_chapter_16
```

当前证据为一个切点明确提升、一个切点不确定、零个明确退步。Branch-first 是下一阶段主方向，但尚未接入 `agent_writer` 默认路径。

## 5. 下一次 clone 后从这里继续

不要修改历史 `runs/pilot_2026-07-13/`；新建独立日期目录并完成剩余四个断点：

```text
after_chapter_01
after_chapter_04
after_chapter_22
after_chapter_26
```

继续生成前先完成两项实验层改进：

1. 把 `conflict_space / trigger / core_mechanism / climax_action / cost_type / end_hook` 加入事件指纹门，任意入围分支对至少三个轴实质不同。
2. Judge 先分别独评每篇正文，再做 pairwise 比较；仍交换候选顺序，映射冲突时必须弃权。

建议的新目录：

```text
experiments/branch_first_v1/runs/full_feasibility_<YYYY-MM-DD>/
```

每个正式 run 至少保存：

- `manifest.json`：相对路径、依赖 run 和模型/策略元数据；
- 公开合同和实际 prompt；
- 候选与 Branch Card；
- 匿名映射和原始 Judge JSON；
- 聚合结果；
- `REPORT.md`；
- 必要的人工标签及其方法说明。

## 归档规则

- `runs/` 是不可变证据；修正协议时创建新 run，不覆盖旧结果。
- 所有 manifest 使用仓库相对路径，不能出现本机绝对路径。
- private gold 必须与 Writer 工作区隔离；可以由已提交源文件重新生成的内容不重复复制。
- `.env`、数据库、缓存、虚拟环境和重复中间产物不入库。
- 报告引用候选时，候选必须随同 run 入库，避免出现只有结论没有证据的提交。
- 每个 run 提交前执行 JSON 解析、敏感信息扫描、对应测试和 `git diff --check`。

## 未归档的旧本地快照

早期 `claudenovel-self-writing-test` 是 IdeaContract 重构前的本地 stub smoke run，包含旧合同 schema、绝对路径、SQLite 和重复候选；它已由当前测试及 `external_idea_mini_2026-07-13` 取代，因此不作为可继续实验的真源。其 `.env`、数据库和缓存不得提交。

