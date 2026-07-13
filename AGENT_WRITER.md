# Agent Writer 体系说明

`agent_writer/` 是 Claudenovel 内的独立写作 agent 子系统，落点是“单章极致质量闭环”，不是通用补文器。

## 设计边界

- 生成前必须有 `writer_strategy`、`reader_expectation_map`、`chapter_contract`、`character_constraints`、`prewrite_plan`。
- 已接受章节、隐藏章节和未来章节都不进入默认生成或返修 prompt；每个单元只以当前外部创意合同为真源。
- 审稿出现 blocking 时不得提交。
- `rewrite` 只服务于修复审稿问题、表达压缩和风格校准，不替代章节合同。
- `commit --approve` 是人工门控，只有通过审稿后才写入 `accepted/`、`commits/` 和审计索引。

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
- `generate-best`：并行生成 2-8 个候选，先过本地硬闸，再由独立 Judge 对匿名合格稿正序/倒序各评一次；胜者不一致时拒绝选优。
- `review`：运行本地质量门禁。
- `rewrite-brief`：生成文件化返修 brief。
- `rewrite`：调用 LLM 按返修 brief 重写。
- `commit --approve`：人工确认后提交章节。
- `status`：查看计数状态。
- `index-report`：查看 SQLite 索引中的产物和 blocking issues。
- `llm-smoke`：验证 LLM 配置可用。

推荐的高质量生成入口：

```powershell
python -X utf8 agent_writer_cli.py --project-root <书项目目录> generate-best --chapter 1 --candidates 3 --candidate-mode diverse
```

该流程采用应用层 `parallel draft → local gate → swapped-order judge`：只有两个及以上候选通过硬闸时才调用 Judge；单一合格稿会直接胜出。`diverse` 使用不同实现策略，`homogeneous` 使用相同中性策略，便于区分角色差异化收益与纯采样收益。它受 DSpark 的 draft/verify 调度启发，但不是 token 级 speculative decoding，会增加候选生成的总 token 成本。

Writer 与 Judge 默认共用 `LLM_*` 配置。需要独立 Judge 模型时可设置 `JUDGE_MODEL`，也可用 `JUDGE_BASE_URL`、`JUDGE_API_KEY`、`JUDGE_TIMEOUT` 覆盖对应配置。

## 状态与索引

每个书项目会生成：

- `story_bible/writer_strategy.json`
- `expectations/reader_expectation_map.json`
- `chapter_contracts/chapter_XXXX_contract.json`
- `chapter_contracts/chapter_XXXX_character_constraints.json`
- `chapter_contracts/chapter_XXXX_prewrite_plan.json`
- `prompts/chapter_XXXX_writer_prompt.md`
- `drafts/chapter_XXXX_draft.md`
- `drafts/chapter_XXXX_candidates/candidate_XX.md`
- `reviews/chapter_XXXX_review.json`
- `reviews/chapter_XXXX_selection.json`
- `accepted/chapter_XXXX.md`
- `commits/chapter_XXXX_commit.json`
- `.agent_writer/index.db`

SQLite 表：

- `chapter_artifacts`：记录 contract、prompt、draft、review、rewrite、commit 路径。
- `review_issues`：记录结构化审稿问题。
- `commit_events`：记录人工确认后的提交事件。

生成 prompt 不读取任何历史章节或长期叙事状态。`review` 会记录正文、合同和角色约束的 SHA-256；`commit` 会重新校验，防止审过 A 稿后误提交 B 稿。
