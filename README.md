# Claudenovel

Claudenovel 现在以“人类创意驱动的单章、短篇与单元剧写作”为主。人类或指定外部来源提供核心想法，Agent 只在明确的自由预算内完成场景、人物行动和文字表达；默认流程不读取前章、不维护跨卷叙事状态，也不提供无人值守续写。

仓库原有的中文小说解析、证据化问答和单章诊断仍可作为只读分析工具使用，但不会自动成为新正文的创意真源。

## 核心流程

```text
外部创意
  → IdeaContract（创意锁 / 禁改项 / 自由预算 / 成功标准）
  → UnitContract + 角色边界 + Prewrite Plan
  → 单稿或并行差异化候选
  → 本地硬闸
  → 独立 Judge 正序/倒序盲评
  → 人工确认
```

设计上的三个硬边界：

- 外部创意排在作者设定和模型偏好的前面。
- 创意锁缺失或出现明确禁改项时，候选不能进入选优。
- Judge 对调候选顺序后胜者变化时，不输出“最佳稿”。

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
