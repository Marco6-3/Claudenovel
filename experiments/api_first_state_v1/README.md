# API-first 单元剧滚动闭环实验

下次直接启动新单元时，先阅读 [`NEXT_RUN.md`](NEXT_RUN.md)，复制任务模板并运行 `run_next_unit.ps1`。该入口先校验 20,000 字上限和 Branch-first 自由轴，再调用现有 CLI；不会自动生成正文或替作者选分支。

## 目的

这个目录保存 `NovelState v1 -> Contextual Scorer -> StateDelta -> UnitArcContract` 第一轮真实 API 探针。它使用独立演示文本，不修改《练气仙诀》正文。

## 输入

- `inputs/chapter_0001.md`：建立左手伤势、整夜未眠、异常清醒、错题本记录和上学行动链。
- `inputs/chapter_0002.md`：人工连续性参照稿；真实 Writer 实验不会把它当成模型输出。

## 真实调用

模型：`deepseek-v4-flash`。

### 第 1 章评分

- 产物：`demo_project/reviews/chapter_0001_contextual_score.json`
- 总分：8.5/10
- confidence：0.55
- blocking：false
- 注意：这是 API teacher 分，不是作者金标。

### 第 1 章状态差量

- 候选：`demo_project/state/deltas/chapter_0001_candidate.json`
- 已应用差量：`demo_project/state/deltas/chapter_0001_applied.json`
- 新状态：`demo_project/state/novel_state_v1.json`
- 结果：证据 ID、逐字引用、段落哈希和权限校验通过，revision 0 -> 1。
- 已知漏项：模型记录了左手伤势、包扎和“解释纱布”线索，但漏掉睡眠债/异常清醒这一持久状态。代码随后增加逐层完整性自检提示，尚待下一轮真实复验。

### 单元剧规划

- 合同：`demo_project/arc_contracts/active_arc.json`
- 本地复审：`demo_project/arc_contracts/arc_0002_a2cb87355f56_review.json`
- 初始探针按五章窗口规划第 2–6 章，只物化第 2 章合同。
- 发现：Planner 把长验收句写进 payoff，并产生“新的微信号”错词。本地复审正确标为 blocking。新代码已把契约拆成短 `required_payoffs` 与详细 `acceptance_criteria`，并增加 Planner 自动返修一次。
- 后续语义已进一步调整：Unit Planner 可按事件自然决定章数，不设八章上限；只约束整个单元预计与实际正文不超过 2 万字。

### 第 2 章真实 Writer

- 正文：`demo_project/drafts/chapter_0002_draft.md`
- 字符数：约 2500
- 结果：正文承接了纱布、错题本、发作间隔和红纹，但章尾重新出现空走廊、声控灯和拉长影子，存在向悬疑氛围回摆的风险。
- 旧本地门禁因为长 payoff 采用字符串匹配而产生大量误报；这不是正文真的漏掉全部 payoff，已通过新契约拆分修正架构。

### 第 2 章真实 Contextual Scorer

- 旧格式问题：请求没有显式关闭 DeepSeek V4 默认思考模式，也没有设置官方 JSON Output。Flash 曾返回空 `content`，Pro 在提高预算后仍把正文对话改写成不存在的“逐字引用”，均不能接收。
- 修正：结构化任务发送 `thinking={"type":"disabled"}` 与 `response_format={"type":"json_object"}`；只有真正 `finish_reason=length` 才提高 token，空 JSON 同预算返修一次。
- 格式修正、但尚未注入作者反馈时：一次返回合法评分卡；总分 9.3/10、文风 9.0，却漏掉作者已明确反对的恐怖回摆。旧评分卡保存为 `demo_project/reviews/chapter_0002_contextual_score_before_author_policy.json`。
- 导入 `author_policy_seed.json` 后，同一正文、同一 Flash 重新评分：总分 8.5、文风 7.0，并逐字引用声控灯和拉长影子，输出 `style.horror_drift` risk。
- 当前产物：`demo_project/reviews/chapter_0002_contextual_score.json`。这证明作者策略进入提示词能修复一个真实漏检，但 API teacher 分仍不是作者 Gold。
- 机器可读前后对照：`author_policy_score_comparison.json`。

### AuthorPolicy v1

- 需求基线：`docs/research/AUTHOR_REQUIREMENTS_AND_EVIDENCE_BASELINE_V1.md`
- 策略种子：`author_policy_seed.json`
- 实际策略：`demo_project/story_bible/author_policy_v1.json`
- Planner、Writer、Scorer、Rewriter 按角色只接收相关规则。
- AuthorPolicy revision 或文件哈希改变后，旧评分卡和旧 ArcContract 不再可直接使用。

### Unit Branch-first 真实探针

- 输入：`unit_branch_demo_intent.json`
- 复现脚本：`run_unit_branch_demo.py`
- 结果报告：`UNIT_BRANCH_RESULTS.md`
- 第一轮六轴字段字面不同，但三条路线实际同构；双顺序语义审计换序不一致，阻断。
- 第二轮给人物与线索 Planner 增加正交机制禁令后，仍收敛为日志、控制变量和相关性确认；语义审计稳定判为同构，继续阻断。
- 没有选择分支、没有激活单元、没有生成正文。结论是 Branch-first 只适用于作者开放至少三个实质自由轴的单元；核心机制已锁定时应直接 `unit-plan`。

## 不能从本实验推出的结论

- 不能据此声称系统已能稳定写完整商业单元。
- 不能把 API 评分当作者金标。
- 不能声称远距离历史检索问题已经解决。
- 不能把演示文本直接并入《练气仙诀》修订章节。
