# 灵感案例库：热门桥段采集、拆解与原创化 brief

这个模块用于把公开网页、论坛讨论、榜单评论或用户口述的高热桥段记录成“可学习的结构机制”。它不保存整章正文，也不要求模型照搬原作，而是把桥段拆成可迁移的创作功能：情绪触发、关系裂痕、地图切换、强弱反转、代价选择、伏笔回收等。

## 适用场景

当你或 agent 想做这些事时使用：

- “帮我生成好的情节想法”
- “找一些热门章节套路让模型学习”
- “收集论坛/网站上讨论很多的章节案例”
- “主角当前地图接近无敌，想自然开启下一个副本”
- “把一个高热桥段改造成我这本书自己的剧情”

## 快速开始

在 `kimi_lab` 根目录执行：

```powershell
python -X utf8 .\inspiration_library.py --help
```

默认输出位置：

```text
novel_inspiration_library/inspiration_library.json
novel_inspiration_library/inspiration_brief.md
```

## 添加一个人工案例

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

```powershell
python -X utf8 .\inspiration_library.py add-url `
  --url "https://example.com/public-discussion" `
  --platform "论坛/榜单/书评站" `
  --tags "高讨论,转折,地图切换"
```

边界：

- 只用于公开可访问网页。
- 不处理付费墙、登录墙、禁止抓取页面。
- 只保存短摘录、来源、热度和机制拆解，不保存整章正文。

## 检索相似桥段

```powershell
python -X utf8 .\inspiration_library.py query `
  "主角当前地图接近无敌，如何用误会、女主离开和上界强者开启新副本"
```

检索会综合：

- 关键词匹配
- 标签
- 热度
- 讨论数
- 评分
- 机制拆解文本

## 生成给写作 agent 的 brief

```powershell
python -X utf8 .\inspiration_library.py brief `
  "基于误会跳崖、上界收徒、主角短期失败，生成 5 个不照搬的开新地图情节" `
  --output ".\novel_inspiration_library\inspiration_brief.md"
```

生成的 brief 会强调：

- 只学习机制，不复用原文表达、专名、完整事件链。
- 必须改造成当前作品的世界观、人物关系和伏笔。
- 需要给后续写作/改写 agent 明确情绪触发、反转、代价、回收方式。

## 和现有分析框架怎么配合

推荐闭环：

1. 先用 `analyze_enhanced.py --common-workflow` 分析当前小说，生成 `editorial_revision_prompt.md`、`llm_source_pack_detailed.md`、RAG/记忆材料。
2. 再用 `inspiration_library.py query` 检索相似高热桥段机制。
3. 用 `inspiration_library.py brief` 生成原创化灵感 brief。
4. 把分析报告和 brief 一起交给续写或章节改写 agent。

这样可以避免“凭空想点子”，也避免“学热门桥段学成抄袭”。
