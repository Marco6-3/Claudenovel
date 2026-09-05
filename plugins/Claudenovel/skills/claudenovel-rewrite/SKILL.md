---
name: claudenovel-rewrite
description: 根据编辑诊断对单章进行审查、改写、生成 diff 和改写报告。适用于用户要求“改这一章”“按报告重写”“先审再改”。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Rewrite

## 目标

对单章文本执行可追踪改写：先诊断，再生成建议，再改写，最后输出 diff 和报告。

作者要求修改完整单元且已有运行记录时，使用 `claudenovel-write` 的新 run-id 与作者反馈流程。只要求评价时使用 `--review-only`。
根据本 SKILL.md 位置向上两级定位插件根目录；从小说项目目录运行以加载其 `.env`，输出放在插件缓存之外。
沿用现有 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 或兼容配置，不自行更换供应商，不展示密钥。

## 输入

- 必须有待改写章节文件，例如 `chapter.txt`。
- 推荐提供作者选定的前文与文风参考，另存为上下文文件；修订早期章节时不要把未来章节作为角色已知经历。
- 可选提供 `memory_summary.json`。

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `rewrite_chapter.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

审查加改写：

```powershell
python -X utf8 "<PLUGIN_ROOT>\rewrite_chapter.py" `
  --chapter-file "<CHAPTER_FILE>" `
  --novel "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>"
```

只审查不改写：

```powershell
python -X utf8 "<PLUGIN_ROOT>\rewrite_chapter.py" `
  --chapter-file "<CHAPTER_FILE>" `
  --novel "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>" `
  --review-only
```

## 验收标准

- 输出目录中必须有诊断、建议、改写正文或 review-only 报告。
- 如果执行改写，必须能看到原文和改写版的差异说明。
- 不要覆盖用户原章节文件，除非用户明确要求。

## 回复用户

汇报改写文件路径、核心修改点、仍需人工确认的问题。不要把整章正文贴进聊天，除非用户要求。
