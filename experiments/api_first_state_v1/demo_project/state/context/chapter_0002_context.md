# 动态叙事上下文

- 目标章节：2
- NovelState revision：1
- 状态同步至：第 1 章
- 状态是否过期：False
- 权限顺序：author_locked > text_confirmed > model_inferred > model_proposed
- model_proposed 默认已排除，不得把模型推测写成既定事实。

## 相关状态

- [authority_layer] [author_locked] 滚动状态闭环演示｜项目核心前提｜高中生凌默在高三学业压力中学习控制图书馆传承造成的身体变化
  - state_id: author.project_premise
  - evidence: 作者锁/无正文证据
  - selected_by: author_locked
- [entity_states] [text_confirmed] 凌默｜凌默体内有传承留下的热流在经脉中乱窜，且左手出现灼痛发作｜凌晨四点以后左手灼痛才慢慢退成麻木；传承留下的热流仍在经脉里乱窜；他不敢继续引气；每次发作时间记在数学错题本最后一页
  - state_id: entity.lingmo.inherited_heat_state
  - evidence: novel-5b4f5b9dd99f:CH0001-P001
  - selected_by: recent_state_change
- [entity_states] [text_confirmed] 凌默｜凌默左手用纱布包扎，带着伤到校｜六点四十五分用纱布包扎左手；七点整带着伤走进教室
  - state_id: entity.lingmo.left_hand_bandaged
  - evidence: novel-5b4f5b9dd99f:CH0001-P002, novel-5b4f5b9dd99f:CH0001-P003
  - selected_by: recent_state_change
- [open_threads] [text_confirmed] 凌默｜凌默尚未想好如何向同桌和班主任解释手上的纱布｜他必须先想好怎样向同桌和班主任解释手上的纱布
  - state_id: open.lingmo.explain_bandage
  - evidence: novel-5b4f5b9dd99f:CH0001-P003
  - selected_by: open_thread

## 最近已接收章节（完整正文）

### 第 1 章

凌晨四点以后，凌默左手的灼痛才慢慢退成麻木。传承留下的热流仍在经脉里乱窜，他不敢继续引气，只把每次发作的时间记在数学错题本最后一页。

六点四十五分，他用纱布包扎左手，套上校服。昨夜没有睡，但身体反常地清醒；脑子能转，眼睛却又干又涩。

七点整，他带着伤走进教室。第一节是语文早读，上午还有两节数学连堂，他必须先想好怎样向同桌和班主任解释手上的纱布。
