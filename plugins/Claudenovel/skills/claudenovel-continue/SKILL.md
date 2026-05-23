---
name: claudenovel-continue
description: 从任务根目录 report.md 中选择后续剧情路线，结合最近章节文风和记忆摘要生成下一章正文。适用于用户要求“续写”“按第几条路线写下一章”“继续写后面剧情”。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Continue

## 目标

基于编辑报告中的后续路线生成下一章，不自由发散，不跳过报告里的 P0 风险。

## 前置条件

- 已有任务根目录 `report.md`，或旧版 `editorial_revision_report.md`。
- 推荐提供全文小说 `.txt`，用于提取最近几章文风。
- 可选提供 `memory_summary.json`。
- `.env` 或环境变量中配置了 DeepSeek/OpenAI 兼容模型。

## 查看可用路线

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `continue_novel.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

```powershell
python "<PLUGIN_ROOT>\continue_novel.py" `
  --report "<OUT_DIR>\\report.md" `
  --list
```

## 生成下一章

```powershell
python "<PLUGIN_ROOT>\continue_novel.py" `
  --report "<OUT_DIR>\\report.md" `
  --route 0 `
  --novel "<NOVEL_TXT>" `
  --lookback 3 `
  --target-words 3000 `
  --chapter-num 0 `
  --out-dir "<OUT_DIR>\\continued"
```

如果用户说“按第 2 条路线”，`--route` 使用 0-based 下标，即第 2 条路线传 `--route 1`。

有记忆文件时：

```powershell
--memory "<OUT_DIR>\\memory_summary.json"
```

## 关键产物

每次续写会生成独立目录，通常包含：

- `chapter_<N>.txt`
- `route_info.json`
- `continuation_prompt.md`

## 验收标准

- `chapter_<N>.txt` 必须存在且非空。
- `route_info.json` 必须记录路线、模型、耗时和生成字符数。
- `continuation_prompt.md` 必须保留完整提示词，方便复盘。
- 如果报告里没有可解析路线，必须先回到 `claudenovel-report` 重新生成合格报告。

## 回复用户

说明使用了哪条路线、章节文件路径、模型名和生成字数。不要声称已经人工精修，除非实际又执行了审查或改写流程。
