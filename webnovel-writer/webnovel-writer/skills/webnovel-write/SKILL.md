---
name: webnovel-write
description: 产出可发布章节，完整执行上下文→起草→审查→润色→提交→备份。
allowed-tools: Read Write Edit Grep Bash Agent
---

# 写章流程

## 目标

产出可发布章节到 `正文/第{NNNN}章-{title}.md`。默认 2000-2500 字，用户/大纲另有要求时从之。

## 模式

| 模式 | 流程 |
|------|------|
| 默认 | Step 0→1→2→2.5→3→4→5→6 |
| `--fast` | Step 0→1→2→2.5→3(轻量)→4→5→6 |
| `--minimal` | Step 0→1→2→2.5→4(仅排版)→5→6 |

## 硬规则

- 禁止并步、跳步、伪造审查
- 必须使用 `Agent` 工具调用指定 subagent；不得用主流程口头代替 subagent 输出
- blocking issue 未解决不进 Step 4/5
- Step 2.5 草稿硬闸未通过不进 reviewer/rewrite/polish；必须带失败原因重生草稿
- 非平凡续写必须读取文件化作者意图：`设定集/author_bible.md` 与 `大纲/chapter_{NNNN}_brief.md`
- 禁止让模型假设已经读过未来章节；隐藏/参考章节只能用于事后评估，不能进入生成或重写 prompt
- 失败只补跑失败步骤，不回退
- 参考资料按步骤按需加载

## 优先级

用户要求 > 状态机硬门槛 > 项目约束（总纲/设定/记忆）> skill 流程 > reference 建议

## CSV 检索（Step 2 按需）

```bash
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table {表名} --query "{关键词}" --genre {题材}
```

触发条件：新角色→命名规则，战斗→场景写法，多角色对话→写作技法，情感描写→写作技法，高频桥段→场景写法。

## 执行流程

### 准备：预检

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?}/skills/webnovel-write"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" placeholder-scan --format text
```

### Step 0：作者设定与章节 brief

非平凡续写（感情线、敌对线、长期伏笔、能力体系、卷级推进）必须先准备或读取作者意图文件：

- `${PROJECT_ROOT}/设定集/author_bible.md`
- `${PROJECT_ROOT}/大纲/chapter_{chapter_num:04d}_brief.md`

如果文件缺失，但用户已经在当前对话给出足够设定，先把设定写入上述 UTF-8 文件再继续。不要把长中文设定塞进 shell inline prompt。

模板：

- `${CLAUDE_PLUGIN_ROOT}/templates/author_bible.template.md`
- `${CLAUDE_PLUGIN_ROOT}/templates/chapter_brief.template.md`

`author_bible.md` 至少包含：主角人设、关键角色人设、关系阶段、世界观边界、禁止新增能力/系统、近 5-10 章方向、风格机制。

`chapter_{NNNN}_brief.md` 至少包含：本章必须节点、禁止节点、人物当前状态、关系证据卡、允许的下一步让步、世界观守门、结尾策略。

### 准备：刷新合同树

genre 从 `.webnovel/state.json` 的初始化配置快照读取，用于刷新合同树；写前主链真源仍是 `.story-system/` 合同。调用 story-system 前必须先从详细大纲解析真实本章目标，禁止传 `{章纲目标}`、`第N章章纲目标` 等占位 query。

```bash
GENRE="$(python -X utf8 -c "import json,sys; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project',{}).get('genre',''))")"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  story-system "${CHAPTER_GOAL}" --genre "${GENRE}" --chapter {chapter_num} --persist --emit-runtime-contracts --format both
```

必备文件：`MASTER_SETTING.json`（调性/禁忌）、`volume_{NNN}.json`（卷级节奏）、`chapter_{NNN}.review.json`（必须节点/禁区）。缺失则阻断。

`chapter_{NNN}.json` 必须优先检查顶层 `chapter_directive`。`chapter_focus` 只能来自 `chapter_directive.goal` 或真实 query，不得从 `dynamic_context` 的参考摘要继承。

写作任务书排序必须固定为：
1. 本章硬性约束：`chapter_directive.goal/time_anchor/chapter_span/countdown/chapter_end_open_question`
2. CBN/CPNs/CEN 与 `must_cover_nodes`
3. 本章禁区：`forbidden_zones`，违反即不通过
4. 风格指引：reasoning、主角卡 OOC 警戒、anti_patterns
5. 场景写法补充：`dynamic_context`，仅作风格参考，不能覆盖章纲约束

### Step 1：context-agent 生成写作任务书

必须使用 `Agent` 工具调用 `context-agent`，不得由主流程自行整理任务书。

```text
Agent(
  subagent_type: "webnovel-writer:context-agent",
  prompt: "chapter={chapter_num}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}; storage_path=${PROJECT_ROOT}/.webnovel; state_file=${PROJECT_ROOT}/.webnovel/state.json（projection/read-model，仅兼容读取）。必须优先读取 ${PROJECT_ROOT}/设定集/author_bible.md 与 ${PROJECT_ROOT}/大纲/chapter_{chapter_num:04d}_brief.md（若存在）；不得假设已读未来章节；先 research，再按 作者意图→本章硬性约束→CBN/CPNs/CEN→本章禁区→关系证据卡→风格指引→dynamic_context补充参考 的顺序输出写作任务书。"
)
```

产物：一份写作任务书，能独立支撑 Step 2 起草。

### Step 2：起草正文

只根据任务书、作者设定文件、章节 brief、已批准的前文证据起草。不加载隐藏/未来章节。不加载 core-constraints/anti-ai-guide（已内化到任务书）。只输出纯正文，无占位符。有结构化节点时围绕 CBN→CPNs→CEN 展开。中文思维写作。

### Step 2.5：草稿硬闸

正文初稿生成后，必须先跑本地硬规则 gate：

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" post-rewrite validate \
  --file "${CHAPTER_FILE}" \
  --out "${PROJECT_ROOT}/.webnovel/tmp/post_generation_validation.json"
```

非零退出或 `blocking=true` 时，停止当前流程。读取 `${PROJECT_ROOT}/.webnovel/tmp/post_generation_validation.json`，把失败原因写回新一轮起草 prompt，重跑 Step 2。禁止把未通过草稿送入 Step 3/4。

当前 blocking 包括：关系角色过早主动求助/依附、主角胁迫/威胁/舆论逼迫/反复堵人、未授权新任务/数值/被动能力系统、缺失本章必要 payoff。

### Step 3：审查

必须使用 `Agent` 工具调用 `reviewer`，不得由主流程伪造审查 JSON。

```text
Agent(
  subagent_type: "webnovel-writer:reviewer",
  prompt: "chapter={chapter_num}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter {chapter_num} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第{chapter_num}章审查报告.md" \
  --save-metrics
```

blocking=true → 修复后重审，不进 Step 4。`--fast` 只检查 setting/timeline/continuity。`--minimal` 跳过。

### Step 4：润色

Step 4 只处理已通过 Step 2.5 与 Step 3 的正文。加载 `polish-guide.md`、`typesetting.md`、`style-adapter.md`。

顺序：post-rewrite 表达压缩/风格校准 → 修复非 blocking issue → 风格适配 → 排版 → Anti-AI 终检。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" post-rewrite rewrite \
  --draft "${CHAPTER_FILE}" \
  --style-sample "${PROJECT_ROOT}/正文/{recent_reference_chapter}.md" \
  --author-settings "${PROJECT_ROOT}/设定集/author_bible.md" \
  --out "${PROJECT_ROOT}/.webnovel/tmp/chapter_rewritten.md" \
  --report-out "${PROJECT_ROOT}/.webnovel/tmp/post_rewrite_report.json" \
  --validate-draft
```

`post-rewrite rewrite` 只改表达、节奏、压缩与风格，不救剧情骨架。如果 `--validate-draft` 阻断，回 Step 2，不得继续润色。

只改表达不改事实。`anti_ai_force_check=fail` 时不进 Step 5。`--minimal` 仅排版。

### Step 5：提交

#### 5.1 Data Agent 提取事实

必须使用 `Agent` 工具调用 `data-agent`，产出 fulfillment_result / disambiguation_result / extraction_result 三份 JSON，并复用 Step 3 的 review_results。

```text
Agent(
  subagent_type: "webnovel-writer:data-agent",
  prompt: "chapter={chapter_num}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。从正文提取事实，生成 .webnovel/tmp/ 下的 fulfillment_result.json、disambiguation_result.json、extraction_result.json；不直接写 state/index/summaries/memory。"
)
```

Data Agent 只提取事实+生成 artifacts，不直接写 state/index/summaries/memory。

#### 5.2 CHAPTER_COMMIT

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {chapter_num} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

自动判定：blocking_count>0 或 missed_nodes 非空 或 pending 非空 → rejected，否则 accepted。

#### 5.3 验证投影

projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

chapter_status 由 projection writer 自动推进：accepted→committed，rejected→rejected。

#### 5.4 失败隔离

commit 未生成→重跑 5.2。projection 失败→只补跑失败项。不回退 Step 1-4。

### Step 6：Git 备份

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" backup \
  --chapter {chapter_num} \
  --chapter-title "{title}"
```

备份必须以解析后的 `PROJECT_ROOT` 为准，禁止从工作区父目录执行裸全量 Git add，避免把书项目仓库作为父仓库的嵌入仓库/submodule 加入。

## 充分性闸门

1. 正文文件存在且非空
2. 审查已落库（`--minimal` 除外）
3. blocking=true 必须停在 Step 3
4. anti_ai_force_check=pass（`--minimal` 除外）
5. accepted CHAPTER_COMMIT，projection 五项 done/skipped
6. chapter_status=committed（projection 自动推进）

## 失败恢复

审查缺失→重跑 Step 3。草稿硬闸失败→回 Step 2 重生草稿。摘要/状态/记忆缺失→重跑 Step 5。润色失真→回 Step 4 修复后重跑 Step 5。
