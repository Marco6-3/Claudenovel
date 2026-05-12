---
name: webnovel-inspiration
description: 采集、拆解和检索高热度网文桥段案例，生成原创化情节灵感 brief。
allowed-tools: Read Bash
---

# /webnovel-inspiration

## 目标

当用户说“帮我找一些好桥段”“学习热门章节套路”“生成好的情节想法”“收集论坛/网站上的高讨论案例”时，使用灵感案例库。

核心原则：**学习机制，不复制正文**。

## Project Root Guard

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## 常用流程

### 1. 添加用户提供的案例

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" inspiration add-manual \
  --title "{案例标题}" \
  --source-url "{来源链接，可空}" \
  --platform "{平台，可空}" \
  --rating "{评分，可空}" \
  --heat "{热度数值，可空}" \
  --discussion-count "{讨论数，可空}" \
  --tags "误会,情感爆点,地图切换" \
  --excerpt "{短摘录或用户概述}" \
  --note "{agent 对桥段机制的观察}"
```

### 2. 从公开 URL 采集短摘录

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" inspiration add-url \
  --url "{公开网页 URL}" \
  --platform "{站点名}" \
  --tags "高讨论,转折,追妻火葬场"
```

只保存短摘录和元数据；不要保存整章正文。

### 3. 检索相似桥段

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" inspiration query \
  "主角当前地图接近无敌，如何用误会、女主离开和上界强者开启新副本"
```

### 4. 生成原创化 brief

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" inspiration brief \
  "基于误会跳崖、上界收徒、主角短期失败，生成 5 个不照搬的开新地图情节" \
  --output "${PROJECT_ROOT}/.webnovel/tmp/inspiration_brief.md"
```

## 输出

- `.webnovel/inspiration_library.json`：案例库
- `.webnovel/tmp/inspiration_brief.md`：可交给计划/写作 agent 的原创化灵感 brief

## 边界

- 不抓取付费墙、登录墙或站点禁止抓取的内容。
- 不保存整章正文。
- 不复用原文表达、专名、完整事件链。
- 热度/评分/讨论数可以作为参考权重，但不能代替 agent 的结构化判断。
