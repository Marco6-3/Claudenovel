---
name: claudenovel-agent-writer
description: 单章高质量写作 agent 工作流，包含自然语言创作入口、章节合同、审稿门禁、作者记忆、章节交接、伏笔账本、分析产物到作者决策候选、工作流评估和记忆变体对比。适用于用户要求“创建一本小说”“做大纲”“规划第几章”“生成正文”“审稿/返修/提交这一章”“查看状态”“单章高质量续写”“作者记忆”“章节交接”“记录后续发展方向/伏笔”“比较记忆变体”“跑 agent_writer 工作流”。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Agent Writer

## 目标

使用插件内 `agent_writer/` 子系统执行“单章极致质量闭环”：先规划章节合同，再写作或导入草稿，随后本地审稿、人工确认提交、记录作者决策，并把确认后的记忆传给下一章。

优先使用 `nl` 子命令处理作者的自然语言请求；只有用户明确要求底层命令，或 `nl` 返回 `missing_fields` 需要补字段时，才拆成具体 CLI 命令。

## 根目录

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `agent_writer_cli.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

所有命令建议使用 UTF-8：

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" <command>
```

## 命令清单

插件同步支持以下 CLI 命令：

- `init`
- `plan`
- `write`
- `review`
- `rewrite-brief`
- `rewrite`
- `commit`
- `generate`
- `llm-smoke`
- `index-report`
- `status`
- `discuss`
- `draft-author-note`
- `record-author-note`
- `handoff`
- `plan-next`
- `experiment`
- `evaluate-workflow`
- `compare-memory-variants`
- `nl`

## 自然语言入口

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" nl --request "创建一本都市异能小说，书名叫《死者订单》，前提是外卖员能听见死者订单，目标读者是男频都市异能读者。"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" nl --request "帮我做第一卷大纲，卷名是死者小区，共20章，核心冲突是死者订单牵出活人骗局；卷末高潮是主角发现最大订单来自自己。"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" nl --request "规划第1章。"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" nl --request "审稿这一章，看看有没有 OOC 和爽点不足。"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" nl --request "我确认，提交这一章。" --allow-commit
```

`nl` 返回结构化 JSON，包含 `intent`、`actions_executed`、`artifacts_written`、`needs_author_input`、`quality_gate` 和 `next_suggested_step`。每次执行都会追加 `state/nl_events.jsonl`。

安全边界：

- 缺字段时只返回 `missing_fields`，不要代替作者猜关键创作字段。
- 提交必须同时有明确确认语义和 `--allow-commit`；review 有 blocking 时必须拒绝提交。
- 模仿具体作者/作品文风或搬运已有正文时，只能提炼高层风格描述，不生成仿写或复刻文本。

## 标准闭环

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" init --name "测试书" --genre "都市异能" --premise "校园灵异" --target-reader "悬疑读者"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" plan --chapter 1 --title "旧楼的第三声铃" --goal "确认铃声来源" --payoff "找到染血校牌" --ending-hook "校牌背面出现主角的名字"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" write --chapter 1 --draft-file "<DRAFT_MD>"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" review --chapter 1
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" commit --chapter 1 --approve
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" draft-author-note --chapter 1 --analysis-dir "<ANALYSIS_DIR>"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" discuss --chapter 1
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" record-author-note --chapter 1 --decision-file "<DECISION_JSON>"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" handoff --chapter 1
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" plan-next --chapter 2 --title "档案室的空座" --goal "追查校牌" --payoff "发现空座名单" --ending-hook "名单被改写"
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" evaluate-workflow --chapter 1
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<BOOK_ROOT>" compare-memory-variants --chapter 1
```

## 作者记忆规则

- `handoff` 必须在 `commit --approve` 后运行，只能基于已接受章节生成。
- `draft-author-note` 只生成候选，不直接写入 `state/`。
- `record-author-note` 是作者确认边界，确认后才会写入作者决策、未来方向、伏笔账本和关系变化。
- 伏笔优先写入 `foreshadowing_decisions`，不要只依赖 `notes` 文本。
- 伏笔账本只增不删；回收或放弃只更新状态。

## 验收标准

- `review` 没有 blocking 后才能 `commit --approve`。
- `handoff` 输出 `handoffs/chapter_XXXX_handoff.json` 和 `.md`。
- `plan-next` 的下一章合同应包含 `previous_handoff`、作者偏好、证据来源和去重后的禁区。
- `evaluate-workflow` 不应出现 fail；risk 需要向用户解释。
- `compare-memory-variants` 中 A 变体应保持 baseline，不混入作者偏好和证据。
