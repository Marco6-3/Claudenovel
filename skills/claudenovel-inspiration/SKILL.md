---
name: claudenovel-inspiration
description: 采集、拆解和检索高热度网文桥段案例，生成不照搬原文的原创情节灵感 brief。适用于用户说“生成好的情节想法”“学习热门章节套路”“收集论坛/网站高讨论案例”“帮我找类似桥段机制”。
allowed-tools: Read Bash
---

# Claudenovel Inspiration

## 目标

当用户想让 agent 学习热门小说章节、论坛讨论或评分较高的桥段时，使用 `Claudenovel` 的灵感案例库。核心原则是：**学习机制，不复制正文**。

这个能力服务于后续写作/改写，不替代 `claudenovel-analyze`。常见顺序是：

1. 用 `claudenovel-analyze` 分析当前小说片段、人物关系和伏笔。
2. 用本 skill 检索或补充相似高热桥段机制。
3. 生成 `inspiration_brief.md`，交给续写、规划或章节改写 agent。

## 入口

在 `Claudenovel` 根目录执行：

```powershell
python -X utf8 .\inspiration_library.py --help
```

默认案例库位置：

```text
novel_inspiration_library/inspiration_library.json
```

## 添加用户提供的桥段

```powershell
python -X utf8 .\inspiration_library.py add-manual `
  --title "误会跳崖触发上界收徒" `
  --tags "误会,情感爆点,地图切换,师徒转折,追妻火葬场" `
  --heat 98000 `
  --discussion-count 3200 `
  --excerpt "主角在当前地图接近无敌，妻子误会他和另一位女性暧昧，在两人曾经甜蜜来过的悬崖求死；崖下空间乱流引来上界大能，前辈看中她天赋准备收徒，主角追来后因实力差距无法阻止，只能接受分离。" `
  --note "机制：旧甜回刺+误会裂痕+地图升级+女主独立成长线+主角短期失败。"
```

## 从公开 URL 采集短摘录

只对公开可访问页面使用：

```powershell
python -X utf8 .\inspiration_library.py add-url `
  --url "https://example.com/public-discussion" `
  --platform "论坛/榜单/书评站" `
  --tags "高讨论,转折,地图切换"
```

注意：只保存链接、元数据、短摘录和机制拆解，不保存整章正文。

## 检索相似机制

```powershell
python -X utf8 .\inspiration_library.py query `
  "主角当前地图接近无敌，如何用误会、女主离开和上界强者开启新副本"
```

## 生成原创化 brief

```powershell
python -X utf8 .\inspiration_library.py brief `
  "基于误会跳崖、上界收徒、主角短期失败，生成 5 个不照搬的开新地图情节" `
  --output ".\novel_inspiration_library\inspiration_brief.md"
```

## 输出边界

- `inspiration_library.json`：案例库，包含来源、热度、标签、短摘录和机制拆解。
- `inspiration_brief.md`：给写作/规划/改写 agent 的原创化灵感 brief。

## 版权和质量边界

- 不抓取付费墙、登录墙或站点禁止抓取的内容。
- 不保存整章正文。
- 不复用原文表达、专名、完整事件链。
- 热度、评分、讨论数只能作为参考权重，不能替代 agent 的结构化判断。
- 生成新情节时，必须先贴合当前作品已有世界观、人物关系和伏笔。
