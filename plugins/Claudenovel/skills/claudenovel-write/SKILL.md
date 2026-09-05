---
name: claudenovel-write
description: 根据作者的单元方案与选定前情起草完整中文小说单元，恢复中断任务，或根据作者反馈另存修订稿。适用于“按方案写完整单元”“写这个故事”“继续上次单元草稿”“按我的反馈修改整稿”。保留原稿，正文候选不自动进入正式小说。
allowed-tools: Read Write Edit Bash
---

# 完整单元写作

## 入口与材料

本技能使用随插件提供的 `agent_writer_cli.py unit-run`。不要把分析报告或历史训练实验当成写作必经步骤。

- 根据当前 SKILL.md 的位置，向上两级定位插件根目录；源码使用仓库根目录。Claude Code 可使用 `CLAUDE_PLUGIN_ROOT`，但必须确认该目录实际包含 `agent_writer_cli.py`。
- `<PROJECT_ROOT>` 使用用户的小说项目目录，放在插件安装目录之外；不要把小说、密钥或输出写入插件缓存。
- 作者提供的方案保存为 UTF-8 Markdown/文本。仅在方案缺少无法推断的核心意图时询问；普通创作留白由模型补全并列入交稿说明。
- 前情、角色设定、文风样例只使用作者明确选定的文件。不要自动拼入旧大纲、其他小说、隐藏参考章或尚未经历的剧情。
- 先阅读随插件提供的 `docs/UNIT_DRAFT_RUNNER.md`，核对参数、成本限制、状态和恢复条件。

## 配置

在小说项目的本地 `.env` 或现有进程环境配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；优先沿用作者已配置的服务，不自动更换供应商。不要读取或展示密钥值。Kimi K3 的可选推理与上下文预检查配置见运行器文档。

所有中文输入通过 UTF-8 文件传递，命令使用 `python -X utf8`。避免将长中文方案塞入 shell 参数。输入已损坏时先修复，不把乱码发送给模型。

## 起草

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" `
  --project-root "<PROJECT_ROOT>" unit-run `
  --run-id unit-01 --brief "<BRIEF_FILE>" `
  --context-file "<SELECTED_CONTEXT_FILE>" --max-chars 29999
```

无前情时省略 `--context-file`；多份选定材料可重复该参数。普通文本方案无需手写 JSON。结构化方案可参考 `examples/unit_brief.json`。

正文硬上限最多 29999 个非空白字符，不保证凑满篇幅。默认最多 40 次逻辑模型调用、两轮机器修订；HTTP 重试可能增加实际请求数。用户另有预算时设置 `--max-calls`、`--max-revision-rounds`，不要为通过检查擅自提高预算。

## 状态、恢复与作者反馈

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" `
  --project-root "<PROJECT_ROOT>" unit-run-status --run-id unit-01
```

输入、代码、配置和已记录输出不变时，以完全相同命令恢复中断任务。修改了任何这些内容，使用新 run-id，不删除恢复记录，不覆盖手工改稿。

作者要求修改已生成整稿时，保留同一方案和选定前情，以新 run-id 使用旧稿：

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" `
  --project-root "<PROJECT_ROOT>" unit-run `
  --run-id unit-02 --brief "<BRIEF_FILE>" `
  --context-file "<SELECTED_CONTEXT_FILE>" `
  --from-run "<PROJECT_ROOT>\drafts\units\unit-01" `
  --revision-note "<AUTHOR_FEEDBACK_FILE>" --max-chars 29999
```

`--from-run` 会触发审阅和有限修订，不是只读审阅。如果用户只要评价，直接只读通读现有整稿，或使用分析/报告技能。用户手工修改过旧运行文件时，不绕过哈希保护；以其确认的稿件另存并开展明确授权的改稿。

## 交稿

检查 `drafts/units/<run-id>/` 下的 `完整单元稿.md`、`交稿说明.md`、`manifest.json`；核对中文、实际状态及正文计数。运行中断且没有完整稿时，明确报告中断，不能宣称交稿完成。

- `awaiting_author`：机器终评无待修问题，仍待作者通读。
- `needs_author_review`：完整候选仍有待审问题。
- `needs_author_direction`：模型提出方向冲突，核对原文后交作者决定。
- `interrupted`：记录原因及可恢复条件。

回复只给整稿与交稿说明链接、核心待决事项、真实验证范围。机器检查不等于文学质量达标。不得自动调用 `commit`、覆盖 accepted 或修改正式状态；作者已经明确批准的操作按其授权执行。

现有逐章项目继续使用原有 `plan / generate / review / rewrite / commit` 流程，见 `AGENT_WRITER.md`；不要强制迁移项目或把整单元候选自动拆入正式正文。
