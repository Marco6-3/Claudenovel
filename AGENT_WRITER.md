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
- `state/agent_writer.db`

SQLite 表：

- `chapter_artifacts`：记录 contract、prompt、draft、review、rewrite、commit 路径。
- `review_issues`：记录结构化审稿问题。
- `state_events`：记录人工确认后的提交事件。
