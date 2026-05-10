---
name: claudenovel-report
description: 基于 claudenovel-analyze 生成的 editorial_revision_prompt.md 调用 DeepSeek/OpenAI 兼容模型，产出具体、尖锐、可执行的编辑诊断报告。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Report

## 目标

调用真实 LLM 生成深度编辑诊断报告。报告必须能指导后续章节改写和续写，不要生成泛泛读后感。

## 前置条件

- 已有 `editorial_revision_prompt.md`。
- `.env` 或环境变量中配置了 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`。
- 推荐模型配置：
  - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
  - `DEEPSEEK_MODEL=deepseek-v4-pro`

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `analyze_enhanced.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

```powershell
python "<PLUGIN_ROOT>\analyze_enhanced.py" `
  --txt-path "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>" `
  --llm-context-report `
  --context-prompt "<OUT_DIR>\\editorial_revision_prompt.md" `
  --llm-output-name "editorial_revision_report.md"
```

## 验收标准

报告合格必须同时满足：

- 包含 `必须修（P0）`、`建议增强（P1）`、`保留但控制（P2）`。
- 核心问题引用 `[CHxxx-Pxxx]` 证据编号。
- 包含逐章或分段改写清单。
- 包含后续剧情路线，每条路线要有冲突核心、人物推进、风险和下一章钩子。
- 报告是给人读的 Markdown，不要强行追加无关 JSON 尾巴。

如果模型调用失败，要明确说明失败原因和已生成的本地产物，不要假装报告已完成。

## 输出

默认输出：

- `editorial_revision_report.md`

向用户回复时给出报告路径、模型名、报告是否通过验收，以及最重要的 P0/P1 摘要。
