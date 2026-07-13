# 《地府微信群》前期留出原章 Benchmark

这个实验在第 2、5、12、17、23、27 章之前切断原文。Writer 只能看到公开状态、紧邻前文和从切点可推出的外部创意；目标原章与原作者路线保存在 private 区，生成完成前不得读取。

## 两条互不混合的分数

- `independent_quality`：上下文连续性、因果推进、人物与世界规则、单元弧、语言和原创性。
- `author_route_alignment`：隐藏原章的叙事功能、具体事件和章末状态。

低路线对齐不等于低质量；它只表示模型选择了不同于原作者的路线。最终还要把原章和生成稿匿名混排，由人类判断更喜欢哪篇。

## 原章可比性规则

只有原章也满足同一份公开外部创意、创意锁和单元范围时，才能把它当作 `independent_quality` 的正式基线。若公开创意要求解决冲突，而原章有意停在开战前的尾钩，原章仍可匿名参加评审并保留诊断分，但必须用 `--ineligible-source original` 排除出正式胜负；这种 hard gate 失败说明测试合同与原章不等价，不能据此宣称模型超过原作者。

`author_route_alignment` 不受此限制：它本来就是测候选对隐藏原作者路线的接近程度。

## 与 DSpark 的关系

[DSpark](https://arxiv.org/abs/2607.05147) 是模型推理层的 speculative decoding：并行起草 token 块，再由目标模型按置信度调度验证长度。这里的“三路 Writer 并行生成 + Judge 选择”是在应用层做 best-of-N 搜索，借用了“先提出多个草案、再验证”的抽象，但不是 DSpark 本身，也不能直接继承它的推理加速结论；它通常用更多总 token 换更高的成稿命中率。

## 构建公开提示词

```bash
python -X utf8 experiments/difu_early_continuation_v1/build_benchmark.py \
  --source apk.tw_地府微信群.txt \
  --out-dir /path/to/benchmark-run
```

只有负责评审的进程才可以增加 `--include-private-gold-text`。Writer 的工作目录和提示词中不得出现 private 路径。

## 首轮实验建议

先运行 `after_chapter_11` 与 `after_chapter_16`：前者测试既有资源参与现实冲突，后者测试新能力首次兑现。每个切点运行 C0 单稿、C1 同质三稿、C2 差异化三稿；确认隔离与评分可靠后，再扩到全部六个切点。
