# Agent Writer 使用说明

`agent_writer/` 是 Claudenovel 新增的独立写作 agent 子系统，用来执行“单章极致质量闭环”。

它不是一个简单的续写脚本，而是先建立作者策略、读者期待、章节合同和角色边界，再调用 LLM 生成草稿，并用本地质量门禁检查后才允许人工确认提交。

更完整的体系说明见仓库根目录的 `AGENT_WRITER.md`。

## 具体结构

`agent_writer/` 不是一个单文件 agent，而是一个文件优先、可审计、可回滚的写作子系统。核心结构如下：

| 文件或目录 | 职责 |
|---|---|
| `cli.py` | 命令行入口。负责解析 `init`、`plan`、`generate`、`review`、`rewrite`、`commit` 等子命令，并把请求转给 `pipeline.py`。 |
| `pipeline.py` | 主编排层。负责初始化项目、生成外部创意合同、组装 prompt、单稿或并行候选生成、Judge 选优、审稿、返修和提交单元。 |
| `models.py` | 数据契约层。用 Pydantic 定义 `AuthorStrategy`、`ReaderExpectationMap`、`ChapterContract`、`CharacterConstraints`、`PrewritePlan`、`ReviewResult`、`ChapterCommit` 等结构。 |
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
  -> expectations/reader_expectation_map.json
  -> .agent_writer/index.db

plan
  -> chapter_contracts/chapter_XXXX_contract.json
  -> chapter_contracts/chapter_XXXX_character_constraints.json
  -> chapter_contracts/chapter_XXXX_prewrite_plan.json

write / generate / generate-best
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

rewrite-brief / rewrite
  -> prompts/chapter_XXXX_rewrite_brief.md
  -> drafts/chapter_XXXX_rewritten.md
  -> drafts/chapter_XXXX_draft.md

commit --approve
  -> accepted/chapter_XXXX.md
  -> commits/chapter_XXXX_commit.json
  -> .agent_writer/index.db.commit_events
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
          -> llm_client.py
          -> index_store.py
```

外部只需要调用 `agent_writer_cli.py`。内部所有命令最终都会进入 `pipeline.py`，再由它协调文件、规则、LLM、质量门禁和 SQLite 索引。

## 核心对象

| 对象 | 生成阶段 | 说明 |
|---|---|---|
| `AuthorStrategy` | `init` | 项目级作者策略，包括题材、前提、目标读者、风格指纹和禁用动作。 |
| `ReaderExpectationMap` | `init` | 读者期待地图，包括承诺收益、爽点循环、钩子策略和禁忌。 |
| `IdeaContract` | `plan` | 外部创意合同。记录人类输入、不可替换的创意锁、禁止改动、自由预算和成功标准。 |
| `UnitContract`（兼容别名 `ChapterContract`） | `plan` | 单元合同。规定本单元目标、必须兑现项、禁止节点、结尾模式和尾钩。 |
| `CharacterConstraints` | `plan` | 单章角色边界。规定角色当前阶段、动机、允许行为、禁止行为、口吻规则和 OOC 红线。 |
| `PrewritePlan` | `plan` | 生成前计划。规定主冲突、场景顺序、必须包含内容、必须避免内容和结尾策略。 |
| `ReviewResult` | `review` | 审稿结果。保存 blocking/risk/warning 问题和返修指令。 |
| `ChapterCommit` | `commit` | 人工确认后的提交记录，记录 accepted 文件、review 文件、contract 文件和状态更新。 |

## 工作流

1. `init` 初始化书项目真值层。
2. `plan` 生成章节合同、角色边界卡和 prewrite plan。
3. `write` 生成写作任务书，或导入外部草稿。
4. `generate` 调用 LLM 生成单一章节草稿；高质量模式用 `generate-best` 并行生成候选、硬闸过滤并由 Judge 匿名正序/倒序复评。胜者不一致时停止选优。
5. `review` 执行本地质量门禁。
6. `rewrite-brief` 生成返修 brief。
7. `rewrite` 调用 LLM 按返修 brief 重写。
8. `commit --approve` 人工确认后提交到 accepted、commits 和 SQLite 审计索引。
9. `index-report` 查看产物索引和 blocking issues。

## 最小闭环示例

在仓库根目录运行：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo init --name "测试书" --genre "都市异能" --premise "主角调查旧楼铃声" --target-reader "男频都市读者"

python -X utf8 agent_writer_cli.py --project-root .agent-demo plan --chapter 1 --title "旧楼的第三声铃" --goal "主角进入旧楼确认铃声来源" --idea "第三声铃只在无人旧楼响起；主角找到染血校牌，背面是自己的名字" --lock "找到染血校牌" --lock "校牌背面出现主角的名字" --payoff "找到染血校牌" --ending-hook "校牌背面出现主角的名字" --character "秦思妍"

python -X utf8 agent_writer_cli.py --project-root .agent-demo llm-smoke
python -X utf8 agent_writer_cli.py --project-root .agent-demo generate-best --chapter 1 --candidates 3 --candidate-mode diverse
python -X utf8 agent_writer_cli.py --project-root .agent-demo review --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo rewrite --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo commit --chapter 1 --approve
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

`generate-best` 是应用层 Best-of-N：候选并行可降低相对串行生成的等待时间，但总 token 通常高于 `generate`。本地硬闸会先淘汰明显违规稿；只有多个候选合格时才调用 Judge，并对调候选顺序复评。`diverse` 测差异化策略收益，`homogeneous` 测纯采样收益。该调度受 DSpark 的 draft/verify 思路启发，不等同于推理引擎里的无损 speculative decoding。

## 产物目录

每个书项目会生成这些目录和文件：

- `story_bible/writer_strategy.json`
- `expectations/reader_expectation_map.json`
- `chapter_contracts/chapter_XXXX_contract.json`
- `chapter_contracts/chapter_XXXX_character_constraints.json`
- `chapter_contracts/chapter_XXXX_prewrite_plan.json`
- `prompts/chapter_XXXX_writer_prompt.md`
- `drafts/chapter_XXXX_draft.md`
- `drafts/chapter_XXXX_candidates/candidate_XX.md`
- `reviews/chapter_XXXX_review.json`
- `reviews/chapter_XXXX_selection.json`
- `accepted/chapter_XXXX.md`
- `commits/chapter_XXXX_commit.json`
- `.agent_writer/index.db`

## 质量边界

- 没有章节合同就不要生成正文。
- 已接受章节、隐藏章节和未来章节都不能进入默认生成 prompt；只使用当前单元外部创意合同。
- 审稿存在 blocking issue 时不要提交。
- `rewrite` 只用于修复审稿问题和风格校准，不替代重新规划。
- `commit --approve` 是人工门控，不应自动跳过。
- `review` 会绑定当前正文、合同和角色约束的 SHA-256；任一产物在审后变化都必须重审，不能提交旧审查对应之外的正文。
