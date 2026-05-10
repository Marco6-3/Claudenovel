---
name: claudenovel-rewrite
description: 根据编辑诊断对单章进行审查、改写、生成 diff 和改写报告。适用于用户要求“改这一章”“按报告重写”“先审再改”。
allowed-tools: Read Write Edit Bash
---

# Claudenovel Rewrite

## 目标

对单章文本执行可追踪改写：先诊断，再生成建议，再改写，最后输出 diff 和报告。

## 输入

- 必须有待改写章节文件，例如 `chapter.txt`。
- 推荐提供全文小说文件作为上下文和文风参考。
- 可选提供 `memory_summary.json`。

## 标准命令

先确定插件根目录：

- Claude Code 中优先使用 `$env:CLAUDE_PLUGIN_ROOT`。
- Codex 或源码调试中，使用包含 `rewrite_chapter.py` 的插件/仓库根目录。
- 下方用 `<PLUGIN_ROOT>` 表示该目录。

审查加改写：

```powershell
python "<PLUGIN_ROOT>\rewrite_chapter.py" `
  --chapter-file "<CHAPTER_FILE>" `
  --novel "<NOVEL_TXT>" `
  --out-dir "<OUT_DIR>"
```

只审查不改写：

```powershell
python "<PLUGIN_ROOT>\rewrite_chapter.py" `
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
