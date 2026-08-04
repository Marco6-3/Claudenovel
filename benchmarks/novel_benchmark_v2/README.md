# Claudenovel Benchmark v2

Benchmark v2 用固定可见上下文、固定标签空间和本地证据校验比较架构版本。它不把 API 自评分当作者 Gold，也不把已出版小说的天然相邻章节当成有信息量的连续性标签。

## 三类任务

- `continuity_detection`：受控注入单一时间、知识、伤势或规则错误，测问题检测与 blocking 漏检。
- `state_delta_coverage`：测伤势、睡眠债、人物知识、关系和开放线索等持久状态是否被完整提取。
- `unit_completion`：逐项判断整个单元是否真正达到作者目标结束状态、payoff 和验收标准。

## 主指标与保护指标

主指标：decision accuracy、blocking escape rate、grounded item rate。

诊断指标：issue/state precision、recall、F1，criterion accuracy，调用延迟。

硬保护：伪造 evidence ID 或逐字引用时，citation validity 低于 1；这种版本不得晋级。作者盲选与人工修改负担尚未进入公开合成集，必须在私有 Author Gold 批次单独统计。

## 运行

```powershell
python -X utf8 agent_writer_cli.py --project-root . benchmark-run `
  --suite .\benchmarks\novel_benchmark_v2\cases\synthetic_controlled_v1.jsonl `
  --out-dir .\benchmarks\novel_benchmark_v2\runs\baseline_v1

python -X utf8 agent_writer_cli.py --project-root . benchmark-score `
  --suite .\benchmarks\novel_benchmark_v2\cases\synthetic_controlled_v1.jsonl `
  --predictions .\benchmarks\novel_benchmark_v2\runs\baseline_v1\predictions.jsonl `
  --report .\benchmarks\novel_benchmark_v2\runs\baseline_v1\report_rescored.json
```

运行目录属于可重建实验产物，不应与 API key 或私有小说正文一起提交。
