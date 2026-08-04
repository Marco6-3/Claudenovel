# Agent Writer 使用说明

`agent_writer/` 是 Claudenovel 的 API-first 滚动时域写作子系统，用来执行“单章极致质量 + 可验证状态更新”闭环。

它不是一个简单的续写脚本，而是先建立作者策略、读者期待、章节合同、角色边界和 `NovelState`，再调用 LLM 生成草稿。草稿需经过本地硬规则和基于前文证据的 API 评分，人工确认后才接收；接收正文必须提取并验证 `StateDelta`，状态同步完成后才能写下一章。

更完整的体系说明见仓库根目录的 `AGENT_WRITER.md`。

## 具体结构

`agent_writer/` 不是一个单文件 agent，而是一个文件优先、可审计、可回滚的写作子系统。核心结构如下：

| 文件或目录 | 职责 |
|---|---|
| `cli.py` | 命令行入口。负责解析 `init`、`plan`、`generate`、`review`、`rewrite`、`commit` 等子命令，并把请求转给 `pipeline.py`。 |
| `pipeline.py` | 主编排层。负责初始化项目、生成外部创意合同、组装 prompt、单稿或并行候选生成、Judge 选优、审稿、返修和提交单元。 |
| `models.py` | 数据契约层。用 Pydantic 定义 `AuthorStrategy`、`ReaderExpectationMap`、`ChapterContract`、`CharacterConstraints`、`PrewritePlan`、`ReviewResult`、`ChapterCommit` 等结构。 |
| `novel_state.py` | 叙事状态层。维护八层 `NovelState v1`、章节证据清单、`StateDelta` 提取与权限校验、状态原子替换和动态上下文编译。 |
| `evidence_graph.py` | 历史证据层。本地事件/证据图生成高召回候选，可用 API 在既有 evidence_id 中重排，排除姓名和词面误命中。 |
| `author_materials.py` | 作者材料层。无额外依赖地提取 `.docx`，登记人物/大纲/历史参考，并强制 `reference_only + explicit_selection_only`。 |
| `benchmark_v2.py` | 回归评测层。分别测连续性缺陷、StateDelta 覆盖和单元完成度，并在本地校验 evidence_id 与逐字引用。 |
| `unit_completion.py` | 单元验收层。独立逐项核验结束状态、payoff 和成功条件，总完成判定由本地程序计算。 |
| `onboarding.py` | 现有小说接入层。按顺序导入权威章节、生成证据清单并可恢复地初始化 StateDelta。 |
| `author_policy.py` | 作者反馈策略层。把作者明确方向、文风偏好、连续性要求和最小修改纪律保存为 `author_locked` 规则，并按角色注入提示词。 |
| `context_scorer.py` | 前文约束评分层。用同一份动态上下文对单稿的连续性、人物知识、时间线、世界规则、关系、伏笔和风格进行证据化评分。 |
| `rolling_arc.py` | 单元剧控制层。把作者给出的下一个单元意图拆成若干 Beat，只激活当前章；每章状态更新后重排剩余 Beat，单元结束后停止并交回作者。 |
| `unit_branch.py` | 可选 Unit Branch-first 层。只在作者开放至少三个事件轴时生成结构化分支卡；六轴字段门和双顺序语义门都通过后才允许作者选择。 |
| `quality_gate.py` | 本地质量门禁。检查必须兑现项、禁止剧情、胁迫式关系推进、未授权系统变更、角色越界、尾钩缺失和常见 AI 味表达。 |
| `llm_client.py` | OpenAI-compatible LLM 客户端。读取环境变量，调用 `/v1/chat/completions`，并提供 `llm-smoke` 连通性测试。 |
| `env.py` | 环境变量加载层。从 `.env`、`agent_writer.env`、`llm.env` 读取 LLM 配置。 |
| `storage.py` | 文件存储工具。统一创建项目目录、读写 UTF-8 文本、读写 JSON、复制草稿文件。 |
| `index_store.py` | SQLite 审计索引层。把单元产物、审稿问题和提交事件写入 `.agent_writer/index.db`，供 `index-report` 查询；不保存叙事记忆。 |
| `rules.py` | 规则包加载层。读取 `rules/*.json`，渲染进写作 prompt。 |
| `rules/` | 调研规则包。保存角色边界、商业章节功能、模块协议和 agent 工作流规则。 |

## 数据流

完整数据流是：

```text
init
  -> story_bible/writer_strategy.json
  -> story_bible/author_policy_v1.json
  -> expectations/reader_expectation_map.json
  -> state/novel_state_v1.json
  -> .agent_writer/index.db

plan
  -> chapter_contracts/chapter_XXXX_contract.json
  -> chapter_contracts/chapter_XXXX_character_constraints.json
  -> chapter_contracts/chapter_XXXX_prewrite_plan.json

write / generate / generate-best
  -> state/context/chapter_XXXX_context.json
  -> prompts/chapter_XXXX_writer_prompt.md
  -> drafts/chapter_XXXX_draft.md

generate-best
  -> drafts/chapter_XXXX_candidates/candidate_XX.md
  -> local blocking gate
  -> Judge 正序/倒序复评
  -> reviews/chapter_XXXX_selection.json
  -> drafts/chapter_XXXX_draft.md（胜出稿）

review
  -> reviews/chapter_XXXX_review.json
  -> .agent_writer/index.db.review_issues

score
  -> prompts/chapter_XXXX_contextual_score_prompt.md
  -> reviews/chapter_XXXX_contextual_score.json

rewrite-brief / rewrite
  -> prompts/chapter_XXXX_rewrite_brief.md
  -> drafts/chapter_XXXX_rewritten.md
  -> drafts/chapter_XXXX_draft.md

commit --approve
  -> accepted/chapter_XXXX.md
  -> state/evidence/chapter_XXXX_evidence.json
  -> state/deltas/chapter_XXXX_sync_task.json（pending_extraction）
  -> commits/chapter_XXXX_commit.json
  -> .agent_writer/index.db.commit_events

extract-state --apply
  -> state/deltas/chapter_XXXX_candidate.json
  -> evidence/hash/authority 校验
  -> state/deltas/chapter_XXXX_applied.json
  -> state/novel_state_v1.json（revision + 1）
  -> sync_task / commit 状态改为 applied

unit-plan / unit-advance
  -> arc_contracts/active_arc.json（一个作者指定的单元剧）
  -> Planner 按总字数预算自然拆章
  -> 本地 Arc Review；长句 payoff、错词、未知 state_id 会被拒绝并自动返修一次
  -> 每次只物化下一个 chapter contract
  -> 单元实际正文达到目标结束状态后停止，等待作者输入下一个单元

material-import / compile-context
  -> Word/UTF-8 作者材料进入 reference-only 注册表
  -> unit-plan / unit-branches 通过 --material-id 显式选择
  -> 本地事件/证据图生成远距离历史候选
  -> 可选 API evidence_id 重排剔除词面误命中
  -> 修订旧章时按目标章开始前投影状态，屏蔽未来事实

unit-completion-score / benchmark-run
  -> 单元结束逐项核验作者验收条件
  -> Benchmark v2 保存 prompt、原始返回、预测和本地证据指标

可选 unit-branches（只在作者开放至少三个自由轴时）
  -> 三个隔离 Planner 生成 UnitBranchCard
  -> 六轴字段差异检查
  -> 匿名正序/倒序语义差异审计
  -> 任一对不足三轴或换序不一致：blocking，不选择
  -> 作者运行 unit-branch-select 选择一个方案
  -> 选中方案才成为 active ArcContract
```

## 层级关系

```text
agent_writer_cli.py
  -> agent_writer.cli
      -> agent_writer.pipeline
          -> models.py
          -> storage.py
          -> rules.py
          -> quality_gate.py
          -> novel_state.py
          -> context_scorer.py
          -> llm_client.py
          -> index_store.py
```

外部只需要调用 `agent_writer_cli.py`。内部所有命令最终都会进入 `pipeline.py`，再由它协调文件、规则、LLM、质量门禁和 SQLite 索引。

## 核心对象

| 对象 | 生成阶段 | 说明 |
|---|---|---|
| `AuthorStrategy` | `init` | 项目级作者策略，包括题材、前提、目标读者、风格指纹和禁用动作。 |
| `ReaderExpectationMap` | `init` | 读者期待地图，包括承诺收益、爽点循环、钩子策略和禁忌。 |
| `AuthorPolicyProfile` | `init` / `policy-add` / `policy-import` | 作者确认的叙事方向、语域、连续性和修订纪律；全部为 `author_locked`。策略变化会使旧评分卡和旧单元计划失效。 |
| `IdeaContract` | `plan` | 外部创意合同。记录人类输入、不可替换的创意锁、禁止改动、自由预算和成功标准。 |
| `UnitContract`（兼容别名 `ChapterContract`） | `plan` | 单元合同。规定本单元目标、必须兑现项、禁止节点、结尾模式和尾钩。 |
| `CharacterConstraints` | `plan` | 单章角色边界。规定角色当前阶段、动机、允许行为、禁止行为、口吻规则和 OOC 红线。 |
| `PrewritePlan` | `plan` | 生成前计划。规定主冲突、场景顺序、必须包含内容、必须避免内容和结尾策略。 |
| `ReviewResult` | `review` | 审稿结果。保存 blocking/risk/warning 问题和返修指令。 |
| `NovelState` | `init` / `extract-state --apply` | 八层叙事状态：Canon Facts、Timeline、Entity State、Character Belief、Relationship Arc、Open Threads、Style Memory、Authority Layer。 |
| `StateDelta` | `extract-state` | 只记录本章造成的持久变化；正文事实必须绑定段落 evidence ID 和哈希。 |
| `ContextualScorecard` | `score` | 基于章节合同、最近已接收正文和有效状态的八维单稿评分卡。 |
| `UnitArcContract`（内部兼容名 `ArcContract`） | `unit-plan` | 只代表一个作者指定的单元剧。章节数可由 Planner 自然决定，预计与实际正文总量均受 2 万字上限约束；记录本单元显式选择的材料 ID。 |
| `AuthorMaterialRegistry` | `material-import` | 保存作者材料哈希、类别和导入文本；材料不自动成为正文事实或作者锁。 |
| `UnitBranchSet` | `unit-branches` | 可选的单元方案集。记录作者开放的自由轴、三张分支卡、六轴差异和双顺序语义审计；不自动替作者选择。 |
| `ChapterCommit` | `commit` | 人工确认后的提交记录，记录 accepted、review、contract、评分卡以及状态同步进度。 |

## 工作流

1. `init` 初始化书项目真值层。
2. 先用 `policy-import` 或 `policy-add` 固化作者反馈；用 `material-import` 建材料库，并只为本单元选择必要的 `--material-id`。若核心机制已锁定，直接用 `unit-plan`；只有作者开放至少三个事件轴时才用 `unit-branches`，并由作者运行 `unit-branch-select` 选定方案。
3. `unit-advance` 只激活当前单元的下一章，生成章节合同、角色边界卡和 prewrite plan。
4. `write` 动态选择作者锁、有效状态和最近 2–3 章完整正文，生成写作任务书；如果前章 `StateDelta` 未同步则停止。
5. `generate` 调用 LLM 生成单一章节草稿；高质量模式用 `generate-best` 并行生成候选、硬闸过滤并由 Judge 匿名正序/倒序复评。胜者不一致时停止选优。
6. `review` 执行本地质量门禁；`score` 调用 API 生成基于前文的证据化单稿评分卡。
7. `rewrite-brief` / `rewrite` 只修当前问题；正文变化后必须重新 `review` 和 `score`。
8. `commit --approve` 人工确认后接收正文并生成证据清单，状态暂记为 `pending_extraction`。
9. `extract-state --completeness-audit --apply` 先提取 `StateDelta`，再运行只补遗漏的第二遍审计，通过 evidence/hash/authority 校验后更新 `NovelState`。
10. 再次运行 `unit-advance`：只重排当前单元的剩余 Beat 并激活下一章。单元结束运行 `unit-completion-score`，然后硬停止，等待作者提供下一个单元意图。
11. `index-report` 或 `status` 查看产物、阻断项、状态 revision 和待同步章节。

作者策略与可选 Branch-first 示例：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo policy-import --file .\author_policy_seed.json

# 核心机制已经明确时，直接 unit-plan。
# 只有作者明确开放至少三个轴时，才生成分支：
python -X utf8 agent_writer_cli.py --project-root .agent-demo unit-branches --start-chapter 1 --target-total-chars 12000 --objective "当前单元目标" --author-intent "作者意图" --freedom-axis conflict_space --freedom-axis cost_type --freedom-axis end_hook
python -X utf8 agent_writer_cli.py --project-root .agent-demo unit-branch-show
python -X utf8 agent_writer_cli.py --project-root .agent-demo unit-branch-select --branch-id branch_02_character
```

如果不想每次手工拼接单元规划参数，可以复制
`experiments/api_first_state_v1/templates/next_unit_request.json`，再运行
`experiments/api_first_state_v1/run_next_unit.ps1`。完整的下次运行清单见
`experiments/api_first_state_v1/NEXT_RUN.md`。这个入口只建立单元方案，不会跳过作者确认直接生成正文。

## 最小闭环示例

在仓库根目录运行：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo init --name "测试书" --genre "都市异能" --premise "主角调查旧楼铃声" --target-reader "男频都市读者"

python -X utf8 agent_writer_cli.py --project-root .agent-demo plan --chapter 1 --title "旧楼的第三声铃" --goal "主角进入旧楼确认铃声来源" --idea "第三声铃只在无人旧楼响起；主角找到染血校牌，背面是自己的名字" --lock "找到染血校牌" --lock "校牌背面出现主角的名字" --payoff "找到染血校牌" --ending-hook "校牌背面出现主角的名字" --character "秦思妍"

python -X utf8 agent_writer_cli.py --project-root .agent-demo llm-smoke
python -X utf8 agent_writer_cli.py --project-root .agent-demo generate-best --chapter 1 --candidates 3 --candidate-mode diverse
python -X utf8 agent_writer_cli.py --project-root .agent-demo review --chapter 1
# 只有 review 指出需要返修时才执行下一行；返修后重新 review
python -X utf8 agent_writer_cli.py --project-root .agent-demo rewrite --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo review --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo score --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo commit --chapter 1 --approve
python -X utf8 agent_writer_cli.py --project-root .agent-demo extract-state --chapter 1 --apply
python -X utf8 agent_writer_cli.py --project-root .agent-demo index-report
```

## LLM 配置

配置从项目根目录 `.env`、`agent_writer.env` 或 `llm.env` 读取，支持以下环境变量：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_KEY=你的 key
```

也可以使用 `OPENAI_*` 或 `LLM_*` 同类变量。

Judge 默认复用 Writer 的 endpoint、模型和 key。可以只覆盖模型，也可以完全分离：

```text
JUDGE_MODEL=更适合评审的模型
JUDGE_BASE_URL=https://api.example.com/v1
JUDGE_API_KEY=你的 judge key
JUDGE_TIMEOUT=120
```

状态提取器和单稿评分器默认复用 Writer 配置，也可以独立覆盖：

```text
STATE_MODEL=低温、擅长 JSON 提取的模型
STATE_TIMEOUT=120
SCORER_MODEL=擅长长上下文评审的模型
SCORER_TIMEOUT=120
```

`STATE`、`SCORER`、`PLANNER`、`JUDGE` 都是结构化 JSON 任务，客户端会使用
`response_format={"type":"json_object"}`。连接 DeepSeek 官方 endpoint 时，默认同时显式发送
`thinking={"type":"disabled"}`，避免 V4 默认思考模式先消耗输出预算；Writer 正文也默认关闭思考，保留温度采样。
如确实需要某个角色使用思考模式，可单独设置，例如 `SCORER_THINKING=enabled`；这时客户端不发送
在思考模式下无效的 `temperature`。非 DeepSeek 兼容 endpoint 默认省略非标准 `thinking` 字段，也可用
`LLM_THINKING=omit` 明确覆盖。

`generate-best` 是应用层 Best-of-N：候选并行可降低相对串行生成的等待时间，但总 token 通常高于 `generate`。本地硬闸会先淘汰明显违规稿；只有多个候选合格时才调用 Judge，并对调候选顺序复评。`diverse` 测差异化策略收益，`homogeneous` 测纯采样收益。该调度受 DSpark 的 draft/verify 思路启发，不等同于推理引擎里的无损 speculative decoding。

## 产物目录

每个书项目会生成这些目录和文件：

- `story_bible/writer_strategy.json`
- `story_bible/author_policy_v1.json`
- `expectations/reader_expectation_map.json`
- `chapter_contracts/chapter_XXXX_contract.json`
- `chapter_contracts/chapter_XXXX_character_constraints.json`
- `chapter_contracts/chapter_XXXX_prewrite_plan.json`
- `prompts/chapter_XXXX_writer_prompt.md`
- `drafts/chapter_XXXX_draft.md`
- `drafts/chapter_XXXX_candidates/candidate_XX.md`
- `reviews/chapter_XXXX_review.json`
- `reviews/chapter_XXXX_selection.json`
- `reviews/chapter_XXXX_contextual_score.json`
- `accepted/chapter_XXXX.md`
- `commits/chapter_XXXX_commit.json`
- `state/novel_state_v1.json`
- `state/state_delta.schema.json`
- `state/context/chapter_XXXX_context.json`
- `state/evidence/chapter_XXXX_evidence.json`
- `unit_branches/<branch_set_id>/branch_XX.json`
- `unit_branches/<branch_set_id>/semantic_diversity_raw_1.txt`
- `unit_branches/<branch_set_id>/semantic_diversity_raw_2.txt`
- `state/deltas/chapter_XXXX_sync_task.json`
- `state/deltas/chapter_XXXX_applied.json`
- `.agent_writer/index.db`

## 质量边界

- 没有章节合同就不要生成正文。
- 默认 prompt 只纳入目标章以前最近 2–3 个已接收章节；未来章节绝不进入上下文。
- `model_proposed` 默认不进入写作上下文；模型推断不能覆盖正文事实，模型不能创建作者锁。
- 前一章状态未同步时不能编译下一章写作 prompt，避免在过期状态上继续滚动。
- 审稿存在 blocking issue 时不要提交。
- 前文评分卡若存在 blocking issue、正文哈希失配或状态 revision 已变化，则不能提交。
- `rewrite` 只用于修复审稿问题和风格校准，不替代重新规划。
- `commit --approve` 是人工门控，不应自动跳过。
- `review` 会绑定当前正文、合同和角色约束的 SHA-256；任一产物在审后变化都必须重审，不能提交旧审查对应之外的正文。
