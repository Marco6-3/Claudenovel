# Claudenovel

Claudenovel 以作者提供的单元剧方案为起点，通过 LLM API 起草小说。新的实验入口 `unit-run` 可以在独立草稿中连续写完整个单元、审阅并有限修订，正文严格小于 3 万非空白字符；它不会自动提交正式正文。原有逐章确认的 `agent_writer` 流程继续保留。

## 完整单元草稿（实验功能）

把单元方案直接保存为 UTF-8 Markdown 或文本，不必手写章节合同：

```powershell
python -X utf8 agent_writer_cli.py --project-root .local_projects/my-novel unit-run --run-id unit-01 --brief 单元方案.md --context-file 前情.md --max-chars 29999
```

结果在项目的 `drafts/units/unit-01/`：阅读 `完整单元稿.md` 和 `交稿说明.md` 即可。原文、修订、模型响应和恢复信息另行留存。工程验证和文学质量验证分开；机器通过不等于作者应当采用。配置、恢复与限制见 [完整单元运行器说明](docs/UNIT_DRAFT_RUNNER.md)，结构化简报示例见 [examples/unit_brief.json](examples/unit_brief.json)。

当前本地写作配置使用 Kimi K3。运行器已加入选择压力、关系发展与带原文证据的阅读效果观察，并支持 K3 输入加输出的 token 预算预检查。它们是写作辅助机制，尚不能保证成熟网文质量；设计、情感记忆方案和验证边界见 [K3 剧情与情感研究](docs/research/KIMI_K3_STORY_AND_EMOTION_2026-09-05.md)。

仓库原有的中文小说解析、证据化问答和单章诊断仍可作为只读分析工具使用，但不会自动成为新正文的创意真源。

## 新单元流程

```text
作者方案与选定前情 → 简短计划 → 完整单元工作稿
  → 按原文审阅 → 有限修订 → 交作者通读
```

作者反馈可通过 `unit-run --from-run 旧运行目录 --revision-note 作者反馈.md` 写入新候选。整个单元写完前不要求逐章正式验收。

## 原有逐章流程

```text
外部创意
  → 作者材料显式选择 + IdeaContract（创意锁 / 禁改项 / 自由预算 / 成功标准）
  → NovelState 时域投影 + 事件/证据图 + API 证据重排
  → Unit ArcContract + 当前章合同 + 角色边界 + Prewrite Plan
  → 单稿或并行差异化候选
  → 本地硬闸
  → 独立 Judge 正序/倒序盲评
  → 人工确认
```

原有流程的设计边界：

- 外部创意排在作者设定和模型偏好的前面。
- 创意锁缺失或出现明确禁改项时，候选不能进入选优。
- Judge 对调候选顺序后胜者变化时，不输出“最佳稿”。
- 旧大纲和人物材料默认只是 `reference_only`；只有显式选择的 material_id 才能进入当前单元。
- 修订早期章节时只使用目标章之前的状态和证据，禁止未来知识倒灌。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

初始化一个单元写作项目：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo init `
  --name "旧楼铃声" `
  --genre "都市悬疑" `
  --premise "一名保安调查无人旧楼的铃声" `
  --target-reader "喜欢有限空间悬疑的读者"
```

把人类想法写成创意合同：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo plan `
  --chapter 1 `
  --title "旧楼的第三声铃" `
  --goal "保安在天亮前确认铃声来源" `
  --idea "第三声铃只在无人时响起；保安找到染血校牌，背面是自己的名字" `
  --lock "找到染血校牌" `
  --lock "校牌背面出现保安的名字" `
  --forbid-change "用系统任务解释铃声" `
  --freedom "校牌主人的身份" `
  --success "结尾完成本单元调查弧" `
  --payoff "找到染血校牌" `
  --ending-hook "校牌背面出现保安的名字" `
  --ending-mode resonant
```

并行写三个差异化候选并盲评：

```powershell
python -X utf8 agent_writer_cli.py --project-root .agent-demo generate-best `
  --chapter 1 `
  --candidates 3 `
  --candidate-mode diverse

python -X utf8 agent_writer_cli.py --project-root .agent-demo review --chapter 1
python -X utf8 agent_writer_cli.py --project-root .agent-demo commit --chapter 1 --approve
```

若要测量“纯采样”而不是差异化角色策略，使用 `--candidate-mode homogeneous`。

## LLM 配置

项目读取项目目录或仓库根目录下的 `.env`、`agent_writer.env`、`llm.env`。支持 OpenAI-compatible 接口：

```text
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=writer-model
LLM_API_KEY=your-key

JUDGE_MODEL=judge-model
JUDGE_BASE_URL=https://api.example.com/v1
JUDGE_API_KEY=your-key
```

Judge 未单独配置 endpoint 或 key 时复用 Writer 配置。`generate-best` 是应用层 Best-of-N，会提高总 token 消耗；它只借用 DSpark 的 draft/verify 调度思想，不是 token 级无损 speculative decoding。

## 实验

首轮实验比较：

- C0：单 Agent 直接写。
- C1：同质 Best-of-N。
- C2：差异化 Best-of-N。
- C3：角色行动模拟后由叙述 Agent 重写。
- C4：C2 胜出稿经过一次限定批评与返修。
- C5：只作为长上下文反证，不进入产品流程。

实验任务、评分树和晋级规则位于 `experiments/single_unit_v1/`；研究依据见 `docs/research/single-unit-writing-experiments.md`。完整历史 run、证据链以及下一次 clone 后的继续顺序见 `experiments/README.md`。

## 只读分析与单章改写

这些入口继续保留，用于理解用户给出的文本或诊断一个现有单元：

- `analyze_enhanced.py`：结构解析、人物关系、情绪与证据包。
- `answer_question.py`：基于 `[CHxxx-Pxxx]` 证据编号回答具体文学问题。
- `rewrite_chapter.py`：在用户指定单章范围内诊断和改写。
- `benchmark_retrieval.py`：评测证据检索。

它们不会自动触发下一章生成。原来的 `continue_novel.py`、`continuation_writer.py` 与 `claudenovel-continue` skill 已移除。

## 项目结构

- `agent_writer/`：外部创意优先的单元写作、硬闸、双顺序 Judge 和人工提交。
- `benchmarks/novel_benchmark_v2/`：连续性、状态完整性和单元完成度的证据约束回归集。
- `experiments/`：实验顺序索引、任务集、可执行工具与不可变历史 run。
- `docs/adr/`：领域与架构决策。
- `docs/research/`：论文依据与实验方案。
- `novel_parser/`：只读解析、证据检索和单章诊断底座。
- `skills/`：面向 Agent 的工作流说明。
- `webnovel-writer/`：历史研究快照，不属于默认写作链，也不应作为无人续写入口。

## 验证

```powershell
python -m pytest -o addopts='' -q
python -m compileall -q agent_writer novel_parser tests
```

更详细的写作链说明见 `AGENT_WRITER.md`，领域术语见 `CONTEXT.md`，架构边界见 `ARCHITECTURE.md`。
