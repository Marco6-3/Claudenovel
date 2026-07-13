# CLAUDE.md

Claudenovel 的默认目标是：基于人类或指定外部来源提供的创意，完成一个高质量单章、短篇或单元剧，不做无人值守长篇续写。

## 不变量

- 外部创意是最高优先级真源。Agent 不得自行替换核心冲突、主题、反转、关系或结局。
- 生成前必须建立 `IdeaContract`，至少包含一个 `idea_lock`。
- 默认生成 prompt 不读取 accepted 历史、章节摘要、关系状态、伏笔账本或未来稿。
- blocking 问题未修复时不得提交；提交必须有显式人工批准。
- 自动 Judge 必须隐藏策略和模型，并对调候选顺序复评。

## 常用命令

```powershell
python -X utf8 agent_writer_cli.py --project-root <DIR> init --name <NAME> --genre <GENRE> --premise <PREMISE> --target-reader <READER>

python -X utf8 agent_writer_cli.py --project-root <DIR> plan --chapter 1 --title <TITLE> --goal <GOAL> --idea <EXTERNAL_IDEA> --lock <IDEA_LOCK> --payoff <PAYOFF> --ending-hook <ENDING>

python -X utf8 agent_writer_cli.py --project-root <DIR> generate-best --chapter 1 --candidates 3 --candidate-mode diverse
python -X utf8 agent_writer_cli.py --project-root <DIR> review --chapter 1
python -X utf8 agent_writer_cli.py --project-root <DIR> commit --chapter 1 --approve

python -m pytest -o addopts='' -q
```

## 只读分析

`novel_parser/`、`analyze_enhanced.py`、`answer_question.py` 可分析用户指定材料。分析结论不得自动注入写作；只有用户确认并写入当前 `IdeaContract` 后，才能成为生成约束。

不要恢复 `continue_novel.py`、`continuation_writer.py`、长期记忆回灌或跨卷自动规划，除非有新的 ADR 明确撤销当前范围决策。
