---
name: claudenovel-report
description: 基于 claudenovel-analyze 生成的 data/editorial_revision_prompt.md 调用 DeepSeek/OpenAI 兼容模型，产出任务根目录 report.md 形式的具体、尖锐、可执行编辑诊断报告。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Report

## 目标

调用真实 LLM 生成深度编辑诊断报告。报告必须能指导当前单元的章节改写，不要生成泛泛读后感或自动规划后续长篇路线。

## 前置条件

- 已有任务文件夹，且其中存在 `data/editorial_revision_prompt.md`。
- 从小说项目目录运行，使用项目 `.env` 或现有进程中的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；也兼容原有 DeepSeek/OpenAI 配置。沿用已配置的供应商，不自行切换模型或展示密钥。
- 根据本 SKILL.md 位置向上两级定位插件根目录。输入和输出放在插件缓存之外。
- 写完整单元使用 `claudenovel-write`，本技能只做诊断。

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `analyze_enhanced.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

```powershell
python -X utf8 "<PLUGIN_ROOT>\analyze_enhanced.py" `
  --txt-path "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>" `
  --organized-output `
  --llm-context-report `
  --context-prompt "<OUT_DIR>\\data\\editorial_revision_prompt.md" `
  --llm-output-name "editorial_revision_report.md"
```

## 验收标准

报告合格必须同时满足：

- 包含 `必须修（P0）`、`建议增强（P1）`、`保留但控制（P2）`。
- 核心问题引用 `[CHxxx-Pxxx]` 证据编号。
- 包含逐章或分段改写清单。
- 包含当前单元的可执行修订方案，每条说明冲突核心、人物行动、风险和局部结尾。
- 报告是给人读的 Markdown，不要强行追加无关 JSON 尾巴。

如果模型调用失败，要明确说明失败原因和已生成的本地产物，不要假装报告已完成。

## 输出

默认输出：

- `report.md`
- 底座数据继续保留在 `data/`

向用户回复时给出报告路径、模型名、报告是否通过验收，以及最重要的 P0/P1 摘要。
