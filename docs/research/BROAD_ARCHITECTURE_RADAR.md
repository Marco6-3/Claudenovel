# Claudenovel Agent 写作：广域论文雷达与架构可能性地图

日期：2026-07-13  
状态：独立研究工作树；未修改生产架构，也不替代上一轮已经收敛的实现建议

## 0. 研究结论先行

这轮调研没有收敛成“再加一种 Agent”。更准确的结论是：小说生成至少由五个彼此不同的问题组成，而论文中的所谓 Agent 往往只解决其中一个。

1. **创意搜索**：在不改写人类核心想法的前提下，找到多种真正不同的实现。
2. **叙事规划**：让事件、人物选择、因果、节奏和兑现形成结构。
3. **长程状态**：维持事实、时间、人物关系、伏笔和世界规则的一致性。
4. **选择与返修**：可靠识别哪一稿更好、哪里需要改，并能回退失败修订。
5. **个体对齐**：学习这位作者和这类读者究竟喜欢什么，而不是追逐通用 Judge 的“高分文”。

因此，下一代 Claudenovel 不应该被预先定义为多 Agent 系统。需要并列保留以下架构族：

- 单模型多输出的创意搜索器；
- 人类导演、模型执行的写作工作室；
- 人物社会模拟器；
- 时间—因果—实体图驱动的叙事引擎；
- 根据任务动态选择模型和计算量的模型组合；
- 用作者反馈训练的个性化写作模型；
- 面向不同读者画像的多目标编辑器。

其中最重要的反证是：[Single-Agent Generation Surpasses Multi-Agent Systems in Semantic Diversity](https://aclanthology.org/2026.findings-acl.1894/) 报告，在匹配提示条件下，单 Agent 生成多个输出的语义多样性高于多 Agent，单次 Multi-Output 还取得最高多样性且没有损害有效性。这意味着“并行 Agent”只是一个待检验实现，不是创造力的默认来源。

同时，[Diversity Collapse in Multi-Agent LLM Systems](https://aclanthology.org/2026.findings-acl.13/) 和 [Divergent Thinking: Escape the Homogeneity Trap](https://aclanthology.org/2026.findings-acl.915/) 都警告：增加 Agent、思维链或通信轮次，可能只增加表面变化，反而让深层语义更快收敛。

对 Claudenovel 最稳固的产品原则仍然是：**人类提供方向和新意，模型负责探索实现、维持结构、暴露风险和提供可比较选择。** 2026 年的人机共写研究也观察到相似分工：人类贡献更多语义新颖性并主导叙事方向，模型主要跟随、扩写和情绪适配（[Directional Alignment and Narrative Agency](https://aclanthology.org/2026.nlp4dh-1.18.pdf)）。

## 1. 本轮范围与证据分级

本轮覆盖 2020–2026 年的一手论文，重点是 2024–2026 年，包含故事生成、长文本、Agent 记忆、多 Agent 拓扑、测试时搜索、自动评审、写作返修、偏好学习和风格建模。综述只用于建立分类，架构判断尽量落到原论文。

证据分为四级：

| 等级 | 定义 | 如何使用 |
|---|---|---|
| A | 直接研究故事/小说生成，并含人评、真实作品或专门基准 | 可进入 Claudenovel 对照实验 |
| B | 直接研究开放式写作、编辑或创意评价，但不是长篇网文 | 可迁移，但需要网文数据复验 |
| C | 来自通用 Agent、记忆、推理、路由或 Judge 研究 | 只形成架构假设，不能直接声称提升小说质量 |
| D | 最新预印本、模型级训练或高成本方案，外部复现不足 | 作为高风险研究仓，不进入默认产品 |

判断“可改进”时同时看四项：是否忠实于外部创意、是否有真正的剧情多样性、是否改善读者质量、是否值得其成本。论文自己的自动分数不直接等价于网文质量。

## 2. 当前架构在地图中的位置

当前系统是：`IdeaContract → UnitContract/角色约束/计划 → 隔离候选 → 本地硬闸 → 调序双 Judge → 人类提交`。

它已经覆盖：

- 人类外部创意是最高真源；
- 同一合同的候选搜索；
- 可确定违规先用本地规则过滤；
- Judge 调序复评并允许不确定；
- 最终由人类接受；
- 产物可审计、可回滚。

尚未决定、也不应一次全部决定的是：

- 搜索应发生在点子、剧情分支、场景、段落还是完整正文；
- 同一模型多采样是否优于多个角色 Agent；
- 什么时候需要角色模拟，什么时候只需直接写；
- 长期状态用摘要、时间线、事件图、知识图还是混合记忆；
- Judge 应代表通用文学质量、作者本人还是不同读者群；
- 返修应该改计划、局部补丁还是全文重写；
- 何时值得微调、DPO/GRPO 或训练专用奖励模型。

这些正是本轮保留开放的变量。

## 3. 十二条架构轴

### 3.1 搜索单位：先探索什么

可选单位不是只有“完整写三篇”。

| 方案 | 机制 | 可能优势 | 主要风险 | 证据 |
|---|---|---|---|---|
| 完整正文 Best-of-N | 同一合同生成 N 篇全文再选 | 简单；可直接比较成品 | 最昂贵；宏观剧情可能高度同质 | B/C |
| 单次 Multi-Output | 一次推理请求返回多个独立候选 | 可能比多 Agent 更有语义多样性；上下文复用 | 输出间仍可能共享锚点 | [Single-Agent Generation](https://aclanthology.org/2026.findings-acl.1894/)（B） |
| Branch/Outline-first | 先搜索互斥剧情机制，再扩写少量分支 | 低成本打开宏观空间 | 好纲未必能变成好文 | [DOME](https://aclanthology.org/2025.naacl-long.63/)、[SuperWriter](https://aclanthology.org/2026.findings-acl.428/)（A） |
| 场景级 Beam/MCTS | 每场景生成动作，评估后逐步扩展 | 可把计算投向关键转折 | 局部评分易导致套路化；状态复杂 | [LongDPO](https://aclanthology.org/2025.findings-acl.395/)、SuperWriter（A/B） |
| 角色行动提案 | 每个角色先提出符合其目标的行动，导演选择 | 人物选择更像因果源而非装饰 | 角色模拟可能破坏整体节奏 | [Character Simulation](https://aclanthology.org/2025.in2writing-1.9/)、[MAGNET](https://arxiv.org/abs/2607.00918)（A/D） |
| 局部句段改写搜索 | 只在被定位的失败处生成替换块 | 成本小、可回退 | 可能修补表面而保留坏结构 | [ART](https://aclanthology.org/2024.naacl-long.327/)（B） |

核心研究问题不是 N 取多少，而是：**哪一级的不确定性最大，就在哪一级分叉。** 创意锁明确但情节机制不明确时，应该搜索分支；情节明确但语言不满意时，才应搜索文本表述。

### 3.2 生成者组织：一个模型、多个 Agent 还是多个模型

| 拓扑 | 适用假设 | 风险 |
|---|---|---|
| 单模型独立多采样 | 随机采样足以覆盖实现空间 | 语义同质；难知道差异来自哪里 |
| 单模型 Multi-Output | 模型可在同一前向上下文中主动分化 | 候选互相感知导致折中，需实测 |
| 同模型、隔离角色 Agent | 明确互斥目标能形成异质通道 | persona 只改变语言，不改变剧情 |
| 异构模型池 | 不同模型有真实能力/偏好差异 | 成本、格式和风格不统一 |
| 稀疏通信 MoA | 只传递可复用信息，避免全文锚定 | 聚合器可能抹平少数派创意 |
| 密集讨论/辩论 | 错误可通过相互质疑修正 | 创作任务会早熟收敛，正确稿也可能被说服放弃 |

[Understanding Agent Scaling via Diversity](https://arxiv.org/abs/2602.03794) 将收益归因于有效异质信息通道，而不是 Agent 数量；[RMoA](https://aclanthology.org/2025.findings-acl.342/) 用嵌入多样性筛选并提取残差信息，说明“保留差异”比让所有 Agent 看完彼此全文更重要。[Talk Isn’t Always Cheap](https://arxiv.org/abs/2509.05396) 与 [Can LLM Agents Really Debate?](https://arxiv.org/abs/2511.07784) 则提供了讨论导致正确答案被多数压力覆盖的间接反证。

对写作的可证伪假设：同预算下比较 `单模型 3 输出`、`3 个隔离 persona`、`3 个不同模型`，只看宏观事件语义簇、作者盲选和最终采用成本。若 persona 条件不增加深层分支数，就不应把它称为多 Agent 创意增益。

### 3.3 计划表示：列表、大纲树、故事线还是图

计划本身可以有四种表示：

1. **线性事件表**：便宜、可读，适合单章。
2. **动态层级大纲**：上层保主题和单元弧，下层随写作展开；[DOME](https://aclanthology.org/2025.naacl-long.63/) 直接支持这一方向。
3. **持续更新的 Storyline + 实体图**：[STORYTELLER](https://aclanthology.org/2025.findings-acl.1071/) 让动态故事线与叙事实体知识图持续交互。
4. **因果/障碍图**：节点不是“发生了什么”，而是“谁因什么目标采取行动，造成什么后果”；[Beyond LLMs: Causal Graph Generation](https://arxiv.org/abs/2504.07459) 的 STAC 表示提供了可解释的因果抽取工具，[Long Story Generation via Knowledge Graph and Literary Theory](https://arxiv.org/abs/2508.03137) 则把障碍框架和知识图用于长故事。

对 Claudenovel 的开放问题是：`PrewritePlan` 应继续是生成提示中的静态文本，还是变成会随章节更新、可被检查的叙事结构。图并不天然优于列表；只有在它能检测“行动没有动机”“伏笔没有后果”“兑现没有来源”时才值得维护成本。

### 3.4 人物自主性与世界模拟

人物模拟不是为了让 Agent “更热闹”，而是把剧情从作者式概述改成角色目标之间的碰撞。

- [Multi-Agent Based Character Simulation](https://aclanthology.org/2025.in2writing-1.9/) 先按时间顺序角色扮演，再将结果改写为符合叙事计划的故事，优于两个故事生成基线。
- [BOOKWORLD](https://aclanthology.org/2025.acl-long.773/) 从小说构建包含动态人物、世界观和地理的 Agent 社会，用于故事生成与交互。
- [RolePlot](https://aclanthology.org/2025.acl-long.603/) 用文学剧本和叙事理论标注评价、增强角色扮演 Agent 的剧情推进。
- [Towards Enhanced Immersion and Agency](https://aclanthology.org/2025.acl-long.546/) 把沉浸感和玩家对故事世界的影响力分开，并用戏剧写作指导和基于剧情的反思改善交互戏剧。
- 最新预印本 [MAGNET/ATLAS](https://arxiv.org/abs/2607.00918) 让角色基于共享世界状态和演化目标提议行动，并用场景级世界表示检测长篇矛盾，属于值得复现但尚未充分独立验证的 D 级路线。

角色模拟最可能在这些章节产生收益：多人物利益冲突、谈判、误解、背叛、关系转折。对纯动作兑现、信息揭示或单人内心戏，固定支付多角色调用成本可能没有价值。

一个关键边界：角色 Agent 只有“行动提案权”，没有改写 IdeaContract 的权力；导演/规划器还必须负责节奏、主题、视角和章节兑现。

### 3.5 长期状态：摘要、时间线、图与记忆策略

“加一个向量库”不足以解决长篇一致性。至少要区分：

- 已确认事实与角色主观信念；
- 当前事件流与长期稳定知识；
- 仍有效事实与已过期但对人物演变有意义的旧状态；
- 文本证据与系统推断；
- 作者锁定设定与模型生成暂定内容。

论文给出多种互相竞争的实现：

| 路线 | 核心机制 | 对小说的迁移假设 |
|---|---|---|
| 动态大纲 + 记忆 | 大纲与写作交织，检索相关历史 | 保持章节目标和前文衔接；DOME（A） |
| 事件图 → 主题图 | 当前事件先进入 progression graph，语义转折时再巩固到长期网络 | 隔离临时噪声与稳定设定；[GAM](https://aclanthology.org/2026.acl-long.1600/)（C） |
| 时间属性图 | 追加式历史，检索时解决冲突 | 表达“曾经如此、现在改变”；[APEX-MEM](https://aclanthology.org/2026.acl-long.749/)（C） |
| 因果时间线 | 保留过期记忆，表示事件演化 | 支持人物关系和线索变化；[THEANINE](https://aclanthology.org/2025.naacl-long.435/)（C） |
| 事实/信念分层 | world、experience、observation、opinion 分网络 | 避免角色知道不该知道的事；[Hindsight](https://aclanthology.org/2026.acl-demo.27/)（C） |
| 学习型记忆策略 | 模型学习何时存、取、改、总结、删 | 可能减少手写策略，但难审计；[AgeMem](https://aclanthology.org/2026.acl-long.981/)（C/D） |
| 离线巩固 | 在线写作与离线记忆整理分离，可用小模型 | 降低主链延迟；[LightMem](https://aclanthology.org/2026.acl-long.588/)（C） |

[ConStory-Bench / Lost in Stories](https://aclanthology.org/2026.findings-acl.410/) 把长篇一致性拆为 5 类、19 个细类，观察到事实和时间错误最常见，错误在叙事中段更集中。可以先借其分类设计本项目错误日志，但不能把论文的自动 Checker 当成真值。

可行的验证不是立刻建立全书知识图，而是对同一批跨章任务比较：最近 K 章全文、层级摘要、时间线、时间—因果图四种上下文，在一致性错误、创意漂移、检索 token 和人工维护成本上的差异。

### 3.6 人类控制与共写界面

两项直接证据支持“人给方向，模型做展开”：

- [Directional Alignment and Narrative Agency](https://aclanthology.org/2026.nlp4dh-1.18.pdf) 发现人类回合引入更多语义新颖性并更常塑造后续发展，模型更多承接和扩写人类引入的元素。
- [Prototypical Human-AI Collaboration Behaviors](https://aclanthology.org/2025.emnlp-main.852/) 在真实写作会话中归纳出多轮协作行为：修改意图、探索多个文本、提问、调风格、注入新内容等。

这提示 Claudenovel 的人机接口不应只有“输入 idea → 收到成文”。可独立研究的交互原语包括：

- 锁定/解锁某个创意原子；
- 指定“只探索，不成文”；
- 对两个 Branch Card 做二选一或都退回；
- 在稿中圈选问题并声明修改意图；
- 明确哪些新内容来自人、哪些来自模型；
- 让模型先问最影响路线的一个问题；
- 保存作者否决过的模式，避免反复建议。

[Plan, Write, Revise](https://aclanthology.org/N19-4016/) 和 [Choose Your Own Adventure](https://aclanthology.org/2021.naacl-main.279/) 也说明，人类在计划、候选选择与修订阶段的选择本身就是重要训练/评估信号。

### 3.7 批评与返修：不是统一的“重写”按钮

返修需要拆成六步：`发现问题 → 说明证据 → 标注意图 → 定位范围 → 生成修订 → 与原稿回归比较/回退`。

- [CritiCS](https://aclanthology.org/2024.emnlp-main.1046/) 在计划和正文阶段使用集体 critics 与 leader，人评显示创造力、吸引力和连贯性提升。
- [ART](https://aclanthology.org/2024.naacl-long.327/) 的核心警告是自我改进不稳定：先判断是否需要修，再比较与信任修订，而不是默认重写必然更好。
- [Help Me Write a Story](https://aclanthology.org/2025.acl-long.1254/) 发现模型反馈可以具体，但常错过最大问题，也难判断何时应该更严厉。
- [Making Revisions Understandable](https://aclanthology.org/2026.findings-acl.1747/) 与 [UniT](https://aclanthology.org/2025.findings-acl.1180/) 支持用“修改意图”而不是笼统好坏来组织编辑。

应该并列实验三类修订：

1. **Plan revision**：正文暂不动，先修场景/因果结构，再重写受影响场景。
2. **Patch revision**：只替换一个可定位片段，适合语言、节奏、设定冲突。
3. **Full rewrite**：只用于结构已经不可局部挽救的情况。

任何修订都需与原稿盲比，并检查创意锁和相邻段落回归；否则 Critic 会成为第二个未经授权的作者。

### 3.8 评审：质量不是一个标量

评审是目前最容易产生虚假进步的部分。

- [LitBench](https://aclanthology.org/2026.eacl-long.362/) 包含 43,827 个训练故事对和 2,480 个测试对；其最强现成 Judge 与人类的一致率约 73%，专门训练的奖励模型约 78%。即使专门基准也远未达到“自动主编”。
- [WritingBench](https://arxiv.org/abs/2503.05244) 使用 1,000 多个真实写作请求和按实例生成的细化标准，提示 rubric 应随任务而变，而不是永远固定六个维度。
- [LLM Comparative Assessment](https://aclanthology.org/2024.eacl-long.8/) 支持成对比较优于直接打分，同时确认位置偏差。
- [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796) 表明多样化小模型评审团可优于单一大 Judge；同一模型多跑几次不等于真正 jury。
- [Reader is the Metric](https://aclanthology.org/2025.findings-acl.1304/) 用 1,471 篇故事和 101 名标注者说明，读者画像可以解释创意写作偏好冲突。
- [Automated Creativity Evaluation Across Open-Ended Tasks](https://aclanthology.org/2026.acl-long.1061/) 把发散创造力表示为语义簇上的熵，把收敛评价交给基于检索的多 Agent Judge。这比词面差异更适合检查“看似三稿、实际同一路线”。

间接但重要的风险来自 [More Convincing, Not More Correct](https://arxiv.org/abs/2607.05904)：在数学与代码任务中，reference-free Judge 配合 Best-of-N 会越来越偏向能说服 Judge 的错误答案。迁移到写作的风险是，系统可能不断选择“流畅、完整、像评分范文”的稿，而不是作者真正想要的稿。

因此评估至少需要四层：

1. 合同硬闸：是否违背人类想法和明确边界；
2. 证据化诊断：时间、事实、因果、人物知识等可定位错误；
3. 成对审美偏好：调序、允许平局/都退回；
4. 作者/目标读者盲选：最终校准 Judge，而非反过来。

### 3.9 读者模型与个体偏好

“网文读者”不是单一 Judge。悬疑读者、爽文读者、角色党和语言党可能对同一稿给出相反偏好。

- [Reader is the Metric](https://aclanthology.org/2025.findings-acl.1304/) 直接支持读者画像化评价。
- [Personality Matters](https://aclanthology.org/2025.emnlp-main.71/) 表明不同用户偏好不同模型，聚合 helpfulness 会掩盖个体差异。
- [Aligning LLMs with Individual Preferences via Interaction](https://aclanthology.org/2025.coling-main.511/) 研究从多轮交互推断未明说偏好。
- [Personalizing LLMs with Binary Feedback](https://aclanthology.org/2026.acl-long.1222/) 用二元反馈学习个人偏好并控制用户间差异。
- [Pearl](https://aclanthology.org/2024.customnlp4u-1.16/) 用与生成效果校准的检索器挑选用户本人写过的文档，适合研究“哪些作者样本最有用”。

对 Claudenovel 的架构分叉是：

- 一个统一 Judge 给所有作品排序；
- 作者专属 Judge；
- 多个读者代理分别评分，输出偏好前沿而非唯一总分；
- 先预测目标读者簇，再选择写法/评审器。

在用户反馈不足时，最安全的是保存成对选择、退回原因和人工改动，不急着训练。偏好模型的价值取决于它能否预测未来选择，而不是复述历史标签。

### 3.10 风格：提示、检索、模块化适配还是强化学习

风格和故事结构应分开测量。[Style over Story](https://aclanthology.org/2026.findings-acl.1361/) 发现多个模型在叙事约束选择中稳定优先 Style，而 Event、Character、Setting 更受模型和提示影响。这意味着 Judge 可能被漂亮语言遮蔽结构问题。

四条路线：

| 路线 | 成本 | 适合阶段 | 证据/风险 |
|---|---:|---|---|
| 明确风格约束提示 | 低 | 数据少、原型期 | 容易变成表面词汇模仿 |
| 检索作者样本 | 中 | 已有合法、明确授权的作者语料 | Pearl；检索错样本会污染内容 |
| 任务模块/LoRA | 中高 | 有稳定题材和足量样本 | [WriterAgent](https://aclanthology.org/2026.findings-acl.968/) 从语言风格、人物、规划到成文做课程学习 |
| 风格 Reward + GRPO | 高 | 可训练开源模型且有可靠风格评审器 | [Capturing Classic Authorial Style](https://aclanthology.org/2026.conll-main.31/) |

反证同样重要：[Catch Me If You Can? Not Yet](https://aclanthology.org/2025.findings-emnlp.532/) 在 400 多位真实作者、每模型 4 万多次生成上发现，少样本上下文学习仍难稳定模仿隐含个人风格。对项目的含义是：不要把少量例文压缩成几个“风格词”后声称已经学会作者。

无论采用哪一路线，都应记录样本来源、授权边界和生成时使用了哪些材料；风格评审不能只用一个与训练奖励同源的分类器。

### 3.11 模型级训练：编排之外的另一条研究线

纯编排并不是终点，但训练线的证据和投入要单独核算。

- [LongWriter](https://arxiv.org/abs/2408.07055) 用 AgentWrite 分解超长任务，并构建 LongWriter-6k 做监督微调。
- [LongDPO](https://aclanthology.org/2025.findings-acl.395/) 用 MCTS 构造逐步偏好对、全局记忆池和 critique-augmented generation。
- [SuperWriter](https://aclanthology.org/2026.findings-acl.428/) 把结构化规划/反思 Agent 与 SFT、层级 DPO、MCTS 信号传播结合。
- [LongWriter-Zero](https://arxiv.org/abs/2506.18841) 用强化学习优化长度、质量和结构。
- [WriterAgent](https://aclanthology.org/2026.findings-acl.968/) 以课程学习和累积 WriterLoRA 分别训练风格、人物、剧情和成文。
- [Sem-DPO](https://aclanthology.org/2026.findings-acl.1184/) 通过惩罚语义漂移，为“不要在偏好优化中偏离人类原始想法”提供了间接思路。
- [Causal DPO](https://aclanthology.org/2026.findings-eacl.58/) 和 [Disentangling Length from Quality in DPO](https://aclanthology.org/2024.findings-acl.297/) 提醒：偏好标签会被题材、风格、用户目标和长度混杂。

训练线的前置条件不是“有很多模型稿”，而是有足够高质量的人类成对选择、退回理由、编辑轨迹和任务上下文。否则训练的只是现有 Judge 的偏见。

### 3.12 测试时计算、动态路由与 DSpark 的正确位置

[DSpark](https://arxiv.org/abs/2607.05147) 是 token/推理引擎层的推测解码思路，不是“几个 Agent 并行写、Judge 选最好”的论文。它可迁移的只是调度原则：先便宜地产生 draft，只验证可能被接受的部分，并根据置信度和负载动态分配计算。

应用层可以有四种对应物：

1. **难度路由**：简单章节单稿，困难章节才多分支；[Scaling LLM Test-Time Compute Optimally](https://arxiv.org/abs/2408.03314)。
2. **预算/质量阈值路由**：先预测用哪个模型、生成多少次；[BEST-Route](https://arxiv.org/abs/2506.22716)。
3. **模型池路由**：[RouteMoA](https://aclanthology.org/2026.acl-long.558/) 用轻量预评分缩小候选模型池，再以评审混合与后验校正排序模型，论文报告在大池场景显著降成本和延迟。
4. **动态验证粒度**：[Variable Granularity Search](https://arxiv.org/abs/2505.11730) 在推理任务中动态选择验证粒度，可迁移为“先检分支、再检场景、最后检全文”。

这条路线追求的是质量—成本—延迟前沿，不直接创造更好的故事。它应该在生成和评审质量可测之后再优化，否则只会更快地选择错误候选。

## 4. 不能同时默认成立的架构选择

以下选择需要 A/B，而不是在架构图里全部叠加：

| 问题 | 路线 A | 路线 B | 决策证据 |
|---|---|---|---|
| 多样性从哪里来 | 单模型 Multi-Output | 多 Agent/多模型 | 深层语义簇、作者盲选、同预算采用率 |
| 剧情由谁推动 | 中央大纲/导演 | 角色目标涌现 | 多人物冲突章的人评；人物因果与节奏同时测 |
| 长期状态是什么 | 可读时间线/摘要 | 图式记忆/学习型策略 | 一致性错误、检索成本、人工维护成本 |
| 先修哪里 | 先修计划 | 直接修正文 | 修订胜率、回归缺陷、创意漂移 |
| 质量是谁的偏好 | 通用文学 Judge | 作者/读者专属 Judge | 对未来人类盲选的预测率 |
| 系统能力来自哪里 | 推理时编排 | SFT/DPO/GRPO | 同数据、同预算下的增益与维护成本 |
| 是否融合候选 | 选一篇并定向修 | 聚合/融合多篇 | 风格统一性、因果回归、相对最佳单稿增益 |
| 计算何时增加 | 固定 N | 不确定性驱动 | 达到同等采用率所需 token/延迟 |

## 5. 七个并列的架构族

这些是研究原型，不是建议把七个都做进产品。

### A. Human Director Studio（人类导演工作室）

`IdeaContract → 多张实现卡 → 人类选路线/补充 → 模型扩写 → 证据化审稿`

- 最适合：外部创意明确、作者希望保有方向控制。
- 核心资产：可读合同、分支卡、局部编辑、完整审计。
- 风险：交互过多，让写作变成表单工作。
- 证据成熟度：A/B，最高。

### B. Single-Model Creative Search（单模型创意搜索器）

`合同 → 单次多输出或独立采样 → 语义聚类 → 只扩展相异候选`

- 最适合：验证多 Agent 是否真的必要，追求低编排复杂度。
- 核心资产：语义多样性度量、重复簇淘汰、预算控制。
- 风险：模型固有偏好仍主导所有候选。
- 证据成熟度：B/C；应作为所有多 Agent 方案的强基线。

### C. Character Society Simulator（人物社会模拟器）

`人物目标/知识/关系 → 隔离行动提案 → 冲突模拟 → 导演选择 → 文学化重写`

- 最适合：群像、关系戏、谈判、背叛、误会。
- 核心资产：人物可知信息、私人目标、共享世界状态。
- 风险：对话冗长、剧情漂移、角色 Agent 越权。
- 证据成熟度：A，但有效范围需按章节类型路由。

### D. Narrative Graph Engine（叙事图引擎）

`事件/行动/后果图 + 时间属性 + 实体状态 → 相关子图检索 → 生成 → 差分更新`

- 最适合：长篇连续写作、复杂伏笔、世界规则密集题材。
- 核心资产：证据引用、时间有效性、事实/信念分离。
- 风险：图抽取错误会变成系统性“伪真相”；维护昂贵。
- 证据成熟度：故事侧 A、记忆侧 C，组合仍需验证。

### E. Adaptive Model Portfolio（自适应模型组合）

`任务特征 → 路由模型/候选数/验证粒度 → 稀疏生成 → 质量—成本选择`

- 最适合：模型供应多、任务量大、成本敏感。
- 核心资产：任务难度预测、各模型能力档案、可比成本日志。
- 风险：路由器错判会在写作前截断最有潜力模型。
- 证据成熟度：C；只有规模化使用后才有价值。

### F. Learned Author Model（学习型作者模型）

`作者样本 + 成对选择 + 编辑轨迹 → 检索/LoRA/DPO/GRPO → 个性化生成`

- 最适合：长期服务同一作者、数据和许可稳定。
- 核心资产：高质量个人反馈，不是合成 Judge 分数。
- 风险：过拟合、偏好漂移、奖励投机、样本来源问题。
- 证据成熟度：B/D；高投入、高上限。

### G. Reader Frontier Editor（读者前沿编辑器）

`候选 → 多个读者画像分别评价 → 输出偏好前沿 → 作者选择目标群`

- 最适合：商业网文、多读者分层、同稿多版本编辑。
- 核心资产：真实读者选择与留存/完读等后验数据。
- 风险：虚构读者 Agent 只是模型刻板印象；迎合指标损害作者性。
- 证据成熟度：B/C；需要真实读者校准。

## 6. 可以组合，但应松耦合

七个架构族中，有四层是相对正交的：

```text
人类控制层        IdeaContract / 选择 / 修改意图 / 最终接受
创意搜索层        Multi-Output / Branch / 角色行动 / 异构模型
叙事状态层        大纲 / 时间线 / 因果图 / 事实与信念
评价学习层        硬闸 / Pairwise / Reader Profiles / 偏好模型
```

合理组合示例：

- Human Director + Single-Model Search：保留人类方向，先用最低复杂度验证分支搜索。
- Human Director + Character Society：只在人物冲突章按需调用模拟器。
- Narrative Graph + Adaptive Routing：只在检索到高风险时间/事实冲突时增加验证。
- Reader Frontier + Learned Author：作者决定要对齐哪个读者群，避免平均偏好吞掉个性。

高风险组合：

- 密集多 Agent 讨论 + 全文融合：最容易多样性塌缩和声音平均化。
- 自动图抽取 + 自动提交：抽取错误会被当成真设定并级联。
- 同源 Writer + 同源 Judge + Best-of-N：容易优化 Judge 偏好而非人类偏好。
- 风格 Reward + 结构 Judge 缺失：可能得到“很像、但不好看”的文章。
- 角色社会完全自治 + 人类创意锁弱化：人物的局部合理行动会吞掉章节承诺。

## 7. 可证伪实验菜单

下面是研究组合，不是单一路线。每项都可以独立否定一个架构假设。

### 低成本：用现有断点和候选完成

| 编号 | 实验 | 对照 | 主要指标 | 否定条件 |
|---|---|---|---|---|
| E1 | 单模型多输出 vs 隔离 persona | 同模型、同总输出 token | 事件语义簇、作者盲选、采用成本 | persona 不增加有效簇或采用率 |
| E2 | 词面多样性 vs 深层多样性 | n-gram/embedding 与人工事件标签 | 语义熵、宏观事件 Jaccard | 词面差异不能预测人工分支差异 |
| E3 | Pointwise vs Pairwise vs Pairwise+弃权 | 同一候选集 | 调序稳定性、人类一致率、校准 | 更复杂 Judge 不提高未来人选预测 |
| E4 | 通用 rubric vs 实例化 rubric | 固定六维 vs 从合同生成标准 | 作者一致率、blocking 漏检 | 实例化标准只抬高分数、无一致率收益 |
| E5 | 返修三分法 | plan、patch、full rewrite | 修订胜率、回归缺陷、修改 token | 某路线净胜率不高于原稿 |

### 中成本：需要新生成，但不训练模型

| 编号 | 实验 | 任务切片 | 主要指标 | 否定条件 |
|---|---|---|---|---|
| E6 | Branch-first vs Full-draft-first | 情节空间开放的章节 | 深层分支数、最终采用率、总 token | 分支变多但成文质量/采用率下降 |
| E7 | 角色模拟按需路由 | 多人物冲突章 vs 单人/动作章 | 人物因果、人评、额外成本 | 两类章节均无交互效应 |
| E8 | 记忆表示对照 | 跨 5/20/50 章的续写 | 事实/时间/人物知识错误、检索 token | 图式记忆不优于可读时间线/摘要 |
| E9 | 因果图 Checker | 有/无 STAC 事件链审查 | 无动机行动、无来源兑现、误报率 | 人工误报过高或无法减少错误 |
| E10 | 异构模型池 | 同预算单模型 vs 多模型 | 质量前沿、风格差异、延迟 | 路由/异构性不提升采用率 |
| E11 | 自适应计算 | 固定 3 稿 vs 置信度追加 | 同采用率所需 token、延迟 | 节省不足或过早停止丢失好稿 |
| E12 | 多读者前沿 | 作者、目标读者簇、通用 Judge | 偏好分歧解释率、真实点击/完读预测 | 模拟画像不能预测真实读者 |

### 高成本：只有积累真实反馈后才做

| 编号 | 实验 | 前置数据 | 成功证据 |
|---|---|---|---|
| E13 | 作者样本检索器 | 授权文本 + 生成效果标注 | 比随机/最近片段检索更能预测作者选择 |
| E14 | 作者偏好 Reward Model | 至少数百到数千个成对选择，含平局/退回 | 留出任务的人类一致率显著高于通用 Judge |
| E15 | WriterLoRA/课程学习 | 稳定题材、人物、风格、计划数据 | 相同推理预算下超过强提示/检索基线 |
| E16 | DPO/GRPO | 去混杂偏好与独立安全/结构评审 | 不以长度、华丽度或 Judge 可说服性换分 |
| E17 | 学习型记忆策略 | 长期交互轨迹和可审计动作标签 | 比规则策略更少错且保持可解释性 |

## 8. 统一测量框架

广泛探索如果每篇论文用自己的分数，最终无法比较。建议所有实验共享以下测量：

### 人类创意忠实度

- Idea Lock blocking 率；
- 禁改项触犯率；
- 人类判断“模型是否偷偷换了核心想法”；
- 修订后新增漂移率。

### 创意搜索质量

- 宏观事件/因果机制语义簇数量；
- 簇熵，而非候选数量；
- 每个簇被人类选中或要求继续发展的比例；
- 新颖但无效、有效但同质分别统计。

### 成文质量

- 人物行动是否由可见目标和信息引起；
- 单元建立—升级—兑现是否闭合；
- 事实、时间、关系、世界规则一致性；
- 语言、节奏、情绪和尾钩；
- 人类盲选允许平局与全部退回。

### 评审可靠性

- 调序一致率；
- Judge—作者与 Judge—目标读者一致率；
- 分数校准，不只看相关系数；
- blocking 漏报/误报；
- Best-of-N 扩大后 Judge 偏好是否漂移。

### 生产价值

- 每篇最终采用稿的总输入/输出 token；
- 墙钟时间和人类等待时间；
- 人工修改字符数、修改回合和编辑时间；
- 采用率、退回率、返修后净胜率；
- 跨章运行后的记忆维护成本。

## 9. 风险雷达与负结果

| 风险 | 早期信号 | 对策/实验 |
|---|---|---|
| 语义多样性塌缩 | 三稿词不同、事件链相同 | 语义簇/事件图；单模型 Multi-Output 强基线 |
| 多数压力 | Agent 修改本来更好的独立提案 | 保持隔离；保存少数派；讨论前后回放 |
| Judge 奖励投机 | N 越大，文越像 rubric 范文但作者越不喜欢 | 不同源 Jury、人类校准、隐藏指标、退回选项 |
| 记忆污染 | 模型推断被写成事实，后续不断引用 | 来源、置信度、事实/信念/提案分层，append-only |
| 过度规划 | 大纲完整但正文机械、缺少局部惊喜 | 保留自由预算；比较动态与静态规划 |
| 角色自治失控 | 局部人物合理但章节不兑现 | 行动提案权与导演裁决分离 |
| 返修退化 | 修掉一个问题又破坏声音或创意锁 | 局部 diff、回归 Gate、原稿/修订盲比、可回退 |
| 风格遮蔽结构 | 华丽稿高分但事件/人物薄弱 | 风格与故事双轨评分；先结构硬检 |
| 个体偏好被平均 | 通用 Judge 高分，作者持续选另一稿 | 作者专属成对数据；读者前沿而非总分 |
| 路由过早停止 | 简单预测错误，未生成潜在好分支 | 保守置信界、抽样探索、记录后悔值 |
| 训练标签混杂 | 模型越来越长、越来越迎合，却不更好 | 长度去偏、任务/用户条件化、留出人评 |

## 10. 研究组合，而非唯一路线

为了与另一个正在实现上一轮建议的工作树保持独立，本工作树建议保留一个“研究投资组合”：

| 研究篮子 | 目的 | 近期可交付 |
|---|---|---|
| 基线与评审可靠性 | 防止所有后续改动建立在不可信分数上 | 单模型 Multi-Output、Pairwise/弃权、作者盲选 |
| 创意搜索 | 判断搜索单位与拓扑 | Branch、完整稿、角色行动三种分叉对照 |
| 叙事状态 | 判断何时从单元升级到长篇 | 时间线/摘要/图的跨章基准 |
| 角色与世界模拟 | 验证人物 Agent 的适用条件 | 多人物冲突章切片实验 |
| 人机共写 | 确保模型放大人的方向而非替换 | 分支选择、修改意图、否决记忆原型 |
| 个体偏好 | 从“通用好文”走向“这个作者会用” | 保存成对选择和真实编辑轨迹 |
| 模型级研究 | 探索长期上限 | 检索器、Reward Model、LoRA/DPO 的数据准备 |

如果需要资源配比，可把约一半研究预算放在基线、评审和数据质量，其余均匀撒在搜索、状态、角色、人机交互和个性化；模型训练保持小额高风险仓。这个分配不是产品路线，只是避免被单篇新论文带偏。

## 11. 如何根据实验结果转向

- 若单模型 Multi-Output 在同预算下不弱于多 Agent：简化默认链，把 Agent 角色留给特殊章节。
- 若 Branch 多样性增加但成文不提升：问题在“纲到文”的条件控制，而非继续增加分支数。
- 若角色模拟只在多人物冲突章有效：做章节分类路由，不做全局默认。
- 若时间线与图记忆效果相当：优先可读、可修的时间线，不为技术复杂度买单。
- 若图记忆显著减少事实/时间错误但引入伪事实：优先改证据与状态治理，而非扩大检索。
- 若 Judge 调序稳定但仍与作者分歧：问题是偏好目标错，不是采样噪声。
- 若作者专属 Judge 只拟合老题材：保留按任务/读者条件化，不升级为全局裁决器。
- 若返修平均不胜原稿：把 Critic 降级为诊断工具，保留人类选择，不自动重写。
- 若固定 N 与自适应 N 质量相同：采用自适应；若频繁后悔，先改不确定性估计。
- 若训练模型只提升同源自动分数：停止训练，回到留出人类盲评。

## 12. 对当前项目最有价值的开放问题

不是“下一步加哪个 Agent”，而是下面这些能改变长期架构的判断题：

1. Claudenovel 的有效多样性究竟来自采样、明确剧情机制、不同模型，还是角色目标冲突？
2. 人类最愿意在哪一层做选择：创意卡、章节纲、场景方案还是完整正文？
3. 作者拒绝一稿时，拒绝的是核心方向、人物选择、节奏、语言还是风格？系统是否能可靠区分？
4. 单元写作升级到连续网文时，最先出现的是事实错误、时间错误、人物知识泄漏还是主题漂移？
5. 哪些章节值得人物模拟，能否在生成前预测？
6. Judge 的分歧代表位置偏差、审美多元、任务标准不清，还是候选确实接近？
7. 作者偏好需要多大数据量才比通用 Judge 更可预测？偏好是否随书、卷和阶段变化？
8. 自动优化会不会把作品推向更流畅、更完整、更像平台平均文，却失去作者的新意？

这些问题的答案将决定 Claudenovel 最终是一个写作流水线、创意搜索器、人物模拟器、叙事数据库，还是作者长期协作模型。

## 13. 论文索引

### 故事与长篇生成

- [Re3: Generating Longer Stories With Recursive Reprompting and Revision](https://aclanthology.org/2022.emnlp-main.296/)
- [DOME: Dynamic Hierarchical Outlining with Memory-Enhancement](https://aclanthology.org/2025.naacl-long.63/)
- [STORYTELLER](https://aclanthology.org/2025.findings-acl.1071/)
- [StoryWriter: A Multi-Agent Framework for Long Story Generation](https://arxiv.org/abs/2506.16445)
- [LongWriter](https://arxiv.org/abs/2408.07055)
- [LongDPO](https://aclanthology.org/2025.findings-acl.395/)
- [LongWriter-Zero](https://arxiv.org/abs/2506.18841)
- [SuperWriter](https://aclanthology.org/2026.findings-acl.428/)
- [WriterAgent / From Style to Story](https://aclanthology.org/2026.findings-acl.968/)
- [A Survey on LLMs for Story Generation](https://aclanthology.org/2025.findings-emnlp.750/)

### 人物、世界与互动叙事

- [Multi-Agent Based Character Simulation for Story Writing](https://aclanthology.org/2025.in2writing-1.9/)
- [BOOKWORLD](https://aclanthology.org/2025.acl-long.773/)
- [RolePlot](https://aclanthology.org/2025.acl-long.603/)
- [Towards Enhanced Immersion and Agency for LLM-based Interactive Drama](https://aclanthology.org/2025.acl-long.546/)
- [MAGNET/ATLAS: From Personas to Plot](https://arxiv.org/abs/2607.00918)
- [Beyond LLMs: A Linguistic Approach to Causal Graph Generation](https://arxiv.org/abs/2504.07459)

### 记忆与长期状态

- [GAM](https://aclanthology.org/2026.acl-long.1600/)
- [APEX-MEM](https://aclanthology.org/2026.acl-long.749/)
- [Hindsight](https://aclanthology.org/2026.acl-demo.27/)
- [THEANINE](https://aclanthology.org/2025.naacl-long.435/)
- [AgeMem](https://aclanthology.org/2026.acl-long.981/)
- [LightMem](https://aclanthology.org/2026.acl-long.588/)
- [RMM: Reflective Memory Management](https://aclanthology.org/2025.acl-long.413/)
- [Lost in Stories / ConStory-Bench](https://aclanthology.org/2026.findings-acl.410/)

### 多 Agent、多样性与路由

- [Single-Agent Generation Surpasses Multi-Agent Systems in Semantic Diversity](https://aclanthology.org/2026.findings-acl.1894/)
- [Diversity Collapse in Multi-Agent LLM Systems](https://aclanthology.org/2026.findings-acl.13/)
- [Understanding Agent Scaling via Diversity](https://arxiv.org/abs/2602.03794)
- [Divergent Thinking: Escape the Homogeneity Trap](https://aclanthology.org/2026.findings-acl.915/)
- [Mixture-of-Agents](https://arxiv.org/abs/2406.04692)
- [RMoA](https://aclanthology.org/2025.findings-acl.342/)
- [RouteMoA](https://aclanthology.org/2026.acl-long.558/)
- [Talk Isn’t Always Cheap](https://arxiv.org/abs/2509.05396)
- [Can LLM Agents Really Debate?](https://arxiv.org/abs/2511.07784)
- [BILLY: activation-space persona blending](https://aclanthology.org/2026.eacl-long.369/)

### 评价、批评与返修

- [LitBench](https://aclanthology.org/2026.eacl-long.362/)
- [WritingBench](https://arxiv.org/abs/2503.05244)
- [Automated Creativity Evaluation Across Open-Ended Tasks](https://aclanthology.org/2026.acl-long.1061/)
- [LLM Comparative Assessment](https://aclanthology.org/2024.eacl-long.8/)
- [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796)
- [Reader is the Metric](https://aclanthology.org/2025.findings-acl.1304/)
- [CritiCS](https://aclanthology.org/2024.emnlp-main.1046/)
- [ART](https://aclanthology.org/2024.naacl-long.327/)
- [Help Me Write a Story](https://aclanthology.org/2025.acl-long.1254/)
- [Beemo](https://aclanthology.org/2025.naacl-long.357/)
- [CoKe](https://aclanthology.org/2025.gem-1.31/)
- [More Convincing, Not More Correct](https://arxiv.org/abs/2607.05904)

### 人类控制、个性化与风格

- [Directional Alignment and Narrative Agency in Human–LLM Co-Writing](https://aclanthology.org/2026.nlp4dh-1.18.pdf)
- [Prototypical Human-AI Collaboration Behaviors](https://aclanthology.org/2025.emnlp-main.852/)
- [Reader is the Metric](https://aclanthology.org/2025.findings-acl.1304/)
- [Personality Matters](https://aclanthology.org/2025.emnlp-main.71/)
- [Aligning LLMs with Individual Preferences via Interaction](https://aclanthology.org/2025.coling-main.511/)
- [Personalizing LLMs with Binary Feedback](https://aclanthology.org/2026.acl-long.1222/)
- [Pearl](https://aclanthology.org/2024.customnlp4u-1.16/)
- [Catch Me If You Can? Not Yet](https://aclanthology.org/2025.findings-emnlp.532/)
- [Capturing Classic Authorial Style with GRPO](https://aclanthology.org/2026.conll-main.31/)
- [Style over Story](https://aclanthology.org/2026.findings-acl.1361/)

### 测试时计算与训练

- [DSpark](https://arxiv.org/abs/2607.05147)
- [Scaling LLM Test-Time Compute Optimally](https://arxiv.org/abs/2408.03314)
- [BEST-Route](https://arxiv.org/abs/2506.22716)
- [Variable Granularity Search](https://arxiv.org/abs/2505.11730)
- [Sem-DPO](https://aclanthology.org/2026.findings-acl.1184/)
- [Causal DPO](https://aclanthology.org/2026.findings-eacl.58/)
- [Disentangling Length from Quality in DPO](https://aclanthology.org/2024.findings-acl.297/)

## 14. 最后的边界说明

本报告刻意没有给出唯一“下一步实现”。上一轮收敛路线已经由另一个工作树执行；这里的价值是保留反例、替代架构和高风险高上限方向，供后续实验结果触发转向。

广域调研后的核心判断是：**不要把 Agent 数量当创新，把可控的搜索空间、可追溯的叙事状态、可靠的人类偏好证据和按需计算当作真正的架构变量。**
