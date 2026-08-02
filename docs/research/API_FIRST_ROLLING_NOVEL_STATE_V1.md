# API-first 滚动时域写作：NovelState v1 实施记录

## 结论

本阶段已把 `agent_writer` 从“章节生成后复制归档”推进为第一版滚动状态闭环：

```text
动态上下文 -> 生成草稿 -> 本地审查 -> 前文约束 API 评分 -> 人工批准
-> 接收正文 -> 章节证据清单 -> StateDelta 提取 -> 证据/权限校验
-> NovelState 原子更新 -> 才允许编译下一章
```

小模型训练不在这条生产主线上。候选稿选优仍由 API Judge 完成；单稿是否与前文连续，则由独立的 Contextual Scorer 读取同一份动态上下文后评分。两者不能互相替代。

## 本阶段实际完成

### 1. NovelState v1 八层状态

`state/novel_state_v1.json` 明确保存：

1. `canon_facts`
2. `timeline`
3. `entity_states`
4. `character_beliefs`
5. `relationship_arcs`
6. `open_threads`
7. `style_memory`
8. `authority_layer`

每条状态都包含 `state_id`、主体、主张、值、权限、置信度、证据、首次出现章、更新章和状态（active/resolved/superseded）。

### 2. 权限不是提示词，而是程序校验

权限顺序固定为：

```text
author_locked > text_confirmed > model_inferred > model_proposed
```

硬约束包括：

- 模型生成的 `StateDelta` 不能创建 `author_locked`。
- 低权限记录不能替换或解决高权限记录。
- `text_confirmed` 和 `model_inferred` 必须绑定段落证据。
- `model_proposed` 默认不进入写作上下文。
- replacement 必须生成新 `state_id`，并明确声明被替代的旧 ID。

### 3. 章节证据与 StateDelta

人工批准章节后，系统把完整正文写入 `accepted/`，并按自然段生成：

```text
state/evidence/chapter_XXXX_evidence.json
```

每段都有稳定 evidence ID、段落号、原文和 SHA-256。`StateDelta` 引用的 ID、段落号、哈希和短引必须与清单一致；本章差量不得引用一个不存在或属于其他章节的证据。

未调用 API 时，章节提交仍可完成，但同步任务会保持 `pending_extraction`。这避免 API 超时破坏人工已经批准的正文，同时下一章写作会被阻止，避免在过期状态上继续滚动。

### 4. 可重放的状态更新

通过校验的差量先写入 `chapter_XXXX_applied.json`，然后使用同目录临时文件加 `os.replace` 原子替换 `novel_state_v1.json`。`delta_id` 具有幂等性，同一差量重复应用不会重复增加 revision 或状态记录。

这不是跨多个文件的数据库事务；它是可重放的文件事务。若进程在 applied delta 写入后、state 替换前停止，可以安全重放同一 delta。

### 5. 动态上下文编译器

当前版本不用“语义相似度 = 相关事实”的方式决定真值。它按以下优先级编译：

1. 作者锁；
2. 显式请求的角色和线索 ID；
3. 活跃 Open Threads；
4. 最近状态变化；
5. 目标章以前最近 2–3 个已接收章节的完整正文。

未来章节不会进入上下文。`model_proposed` 被排除。上下文记录 state revision 和同步截止章，供写作器与评分器共同使用。

### 6. 基于前文的单稿评分器

`score` 与 Best-of-N Judge 分工如下：

| 组件 | 输入 | 目标 |
|---|---|---|
| Best-of-N Judge | 同一任务书下的多个候选 | 候选间选优，且正序/倒序复评 |
| Contextual Scorer | 单一草稿 + 章节合同 + 动态前文上下文 | 判断该稿是否与前文、人物状态和未结线索一致 |

Contextual Scorer 的八个维度为：

- `contract_fidelity`
- `boundary_continuity`
- `character_state_and_knowledge`
- `timeline_and_causality`
- `world_rule_resource_and_injury`
- `relationship_and_open_threads`
- `style_and_voice`
- `payoff_and_readability`

总分由本地代码按固定权重计算，不接受模型自报总分。模型引用的前文 evidence ID、state ID 和本章短引都会被程序校验。伪造引用会导致整份评分卡拒收。

评分卡存在时，提交还会校验：草稿哈希未变化、NovelState revision 未变化、动态上下文未变化，并且没有 blocking 问题。

## UnitArcContract 与滚动控制器

第二轮实现已增加 `UnitArcContract`（内部保留 `ArcContract` 兼容名）。它只表示作者指定的“下一个单元剧”，不是开放式自动连载计划。

作者输入至少包括单元目标与作者意图，还可以补充入口状态、目标结束状态、单元 payoff、锁和禁止改动。Planner 按事件自然拆成若干 Beat；章节数不是固定上限。系统约束的是单元预计正文与实际已接收正文均不超过 2 万字：每个 Beat 有 `target_chars`，总和必须在预算内；每次提交还会按真实正文字符数累计检查。

生产规则是：

1. `unit-plan` 只规划当前单元，不能规划单元后的新主线。
2. `unit-advance` 每次只把一个 Beat 物化成章节合同。
3. 章节接收并应用 `StateDelta` 后，剩余 Beat 必须按新 revision 重排。
4. 最后一章达到目标结束状态后停止，返回 `stop_and_request_next_unit_intent`，等待作者输入下一个单元。

初次真实 N=5 探针发现 Planner 把长篇验收说明直接塞进 `required_payoffs`，并生成错词“新的微信号”。因此新增 `ArcPlanReview`：payoff 必须是短事件标签，详细条件进入 `acceptance_criteria`；明显错词、未知 state_id 和非原子 payoff 会阻断激活，并把具体错误反馈给 Planner 自动返修一次。

## 真实 API 探针结果

使用 `deepseek-v4-flash` 在隔离演示项目中完成：

- 第 1 章 Contextual Score：8.5/10，confidence 0.55，无 blocking。
- 第 1 章 StateDelta：通过 schema、段落 ID、逐字引用、段落哈希与权限校验，state revision 从 0 更新到 1。
- 第 1 章提交后、差量应用前，第 2 章上下文编译被正确阻断；差量应用后恢复。
- Planner 生成了一个五 Beat 单元计划，控制器只物化第 2 章合同，没有提前物化第 3–6 章合同。
- Writer 生成第 2 章约 2500 字正文；本地旧式字符串门禁对语义已兑现的长 payoff 产生大量误报，促成了“短 payoff + acceptance criteria”的契约拆分。
- 第 2 章旧请求格式未显式关闭 DeepSeek V4 默认思考模式，也未开启官方 JSON Output。结果先后出现空 `content` 和拼接改写的伪逐字引文；单纯增加 `max_tokens` 或改用 Pro 都没有解决证据违规。
- 客户端现对结构化角色显式发送 `thinking: disabled` 与 `response_format: json_object`；只在 `finish_reason=length` 时增加 token，空 JSON 响应改为同预算提示返修一次。
- 修正格式后，同一个第 2 章评分任务由 `deepseek-v4-flash` 一次返回完整 JSON，并通过 evidence ID、state ID 和逐字引文校验：9.3/10，confidence 0.95，无 blocking。该分数仍只是 teacher/Silver 信号。

这些结果是架构探针，不是小说质量结论。尤其 API 分数仍属于 teacher/Silver 证据，不能代替作者最终判断。

## AuthorPolicy 与历史实验复用

此前本地连续性模型三种子 test F1 只有 `0.549 ± 0.068`，不进入写作链；但作者真实反馈仍然是最高价值数据。本轮新增 `AuthorPolicy v1`：

- 作者方向、语域、连续性和最小修改纪律保存为独立 `author_locked` 规则；
- 按角色分别注入 Planner、Writer、Scorer、Rewriter；
- 风格问题与连续性标签分离；
- 策略 revision 或哈希变化后，旧评分卡和旧单元计划自动失效。

真实前后对照中，第 2 章旧评分为 9.3、文风 9.0，未识别章尾声控灯和拉长影子；导入作者策略后，同一模型把总分降为 8.5、文风降为 7.0，并输出 `style.horror_drift` risk。正文没有被自动修改。

## 可选 Unit Branch-first

Branch-first 两轮真实探针进一步收敛了使用边界：

1. 六轴字段字面差异会把同构路线误判成多样；因此增加匿名正序/倒序语义审计。
2. 换序不一致、任意一对少于三个实质差异轴，都把整个分支集标为 blocking。
3. 当作者已经锁定“控制变量确认图书馆关联”等核心机制时，强行制造三种核心机制会覆盖作者意图；这种任务应直接 `unit-plan`。
4. `unit-branches` 现在要求作者显式开放至少三个自由轴，分支只探索自由预算，不改写作者锁。
5. 分支集通过后仍不自动选择，必须由作者运行 `unit-branch-select`。

两轮真实分支均被正确阻断，未激活 ArcContract、未生成正文。详见 `experiments/api_first_state_v1/UNIT_BRANCH_RESULTS.md`。

## 当前仍未完成

- 远距离证据选择仍是显式实体/线索 + 活跃状态 + 最近完整章节，不是已经验证过的历史事件检索器。
- 还没有在《练气仙诀》正式章节上完成“单元意图 -> 完整单元 -> 作者验收”的端到端试验。
- StateDelta 首次真实提取漏掉了“睡眠债/异常清醒”这一持久状态；提示词已加入逐层完整性自检，但仍需下一轮真实提取验证。
- Unit Planner 的目标结束状态是否在最后一章真正兑现，目前依赖 Contextual Scorer 与作者验收，尚缺独立的单元完成评分卡。
