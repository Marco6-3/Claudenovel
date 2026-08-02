# 下次直接使用：API-first 单元剧入口

这套入口把本轮已经验证的 `AuthorPolicy -> NovelState -> 单元规划 -> 单章生成/评分 -> 人工确认 -> StateDelta` 串成固定操作顺序。它面向“作者给出下一个单元意图”，不是连续自动写几十章。

## 1. 一次性准备

1. 在仓库根目录 `.env` 配置 Writer、Planner、Scorer 和 State Extractor。不要把 API key 写进任务 JSON 或提交到 Git。
2. 如果是新书项目，先执行 `init`；现有项目不要重复初始化。
3. 把作者长期要求整理到一个 `author-policy/v1` JSON，规划前用 `policy-import` 导入。示例可参考本目录的 `author_policy_seed.json`。

```powershell
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project init --name "书名" --genre "类型" --premise "核心前提" --target-reader "目标读者"
```

## 2. 填写本次单元任务

复制 `templates/next_unit_request.json`，只修改副本：

- `target_total_chars` 是整个单元的正文目标，上限 20,000 字；不硬性限定章数。
- 核心机制、关键人物选择或因果链已经确定时，把 `core_mechanism_locked` 设为 `true`，使用直接规划。
- 只有确实开放至少三个事件轴时才使用 Branch-first。此时参考 `templates/next_unit_request_branch.json`，可选轴只有 `conflict_space`、`trigger`、`core_mechanism`、`climax_action`、`cost_type`、`end_hook`。
- `unit_payoffs` 写具体必须发生的事；`success_criteria` 写人工能判断通过/不通过的验收条件。不要用“更精彩”“更自然”这类无法核验的空话。

先做零 API 校验：

```powershell
powershell -ExecutionPolicy Bypass -File .\experiments\api_first_state_v1\run_next_unit.ps1 `
  -ProjectRoot C:\path\to\book_project `
  -RequestFile C:\path\to\my_next_unit.json `
  -ValidateOnly
```

校验通过后生成单元方案：

```powershell
powershell -ExecutionPolicy Bypass -File .\experiments\api_first_state_v1\run_next_unit.ps1 `
  -ProjectRoot C:\path\to\book_project `
  -RequestFile C:\path\to\my_next_unit.json `
  -PolicyBundle C:\path\to\author_policy.json
```

这个入口只规划，不生成正文。`auto` 会在“核心机制未锁定且开放轴不少于三个”时选择 Branch-first，否则直接生成单元合同。

## 3. 作者确认后才写

直接规划：先复审合同，再激活当前单元的第一章。

```powershell
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-review
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-advance
```

Branch-first：先查看 `unit_branches/latest_branch_set.json` 及语义差异审计。若被标为 blocking，不要硬选；收紧或重新开放真正不同的机制后再生成。审计通过后仍由作者手工选择：

```powershell
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-branch-show
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-branch-select --branch-id branch_02_character
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-advance
```

## 4. 每章固定闭环

```powershell
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project generate-best --chapter 2 --candidates 3 --candidate-mode diverse
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project review --chapter 2
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project score --chapter 2
```

人工阅读草稿、前一章和后一章意图。需要修改时，只修当前已确认的问题；修改后重新 `review` 和 `score`。只有人工通过后：

```powershell
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project commit --chapter 2 --approve
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project extract-state --chapter 2 --apply
python -X utf8 agent_writer_cli.py --project-root C:\path\to\book_project unit-advance
```

`extract-state --apply` 未完成时，系统会阻止下一章在过期状态上继续生成。`unit-advance` 只激活下一个 Beat；整个单元完成后停止，等待作者给出下一单元意图。

## 5. 这次留下的可复用结果

- `docs/research/AUTHOR_REQUIREMENTS_AND_EVIDENCE_BASELINE_V1.md`：作者需求和历史证据基线。
- `docs/research/API_FIRST_ROLLING_NOVEL_STATE_V1.md`：架构、协议、边界和实验结论。
- `author_policy_seed.json`：可直接导入的作者策略种子。
- `author_policy_score_comparison.json`：同一稿件注入作者策略前后的真实评分对照。
- `demo_project/`：NovelState、Contextual Scorer、StateDelta 和单元规划的完整审计产物。
- `UNIT_BRANCH_RESULTS.md` 与 `unit_branch_demo_project/`：Branch-first 两轮真实失败案例，保留其阻断证据，避免以后把字段差异误当成剧情差异。

这些实验结果只证明协议和某些失败门禁有效，不等于系统已经稳定产出商业质量单元；API 评分仍是 teacher 信号，不是作者金标。
