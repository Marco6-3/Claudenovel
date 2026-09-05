# Claudenovel 写作插件

从作者方案和选定前情起草完整单元，按反馈另存修订稿；分析、证据问答和单章改写作为辅助工具保留。插件自带运行代码，不依赖仓库中的小说原文、实验目录或旧写作系统。

## 工作流

| 需求 | 技能 |
|---|---|
| 写完整单元、恢复草稿、按反馈修订整稿 | `claudenovel-write` |
| 读前文、分析人物与情节、核对文学问题 | `claudenovel-analyze` |
| 生成带证据的编辑诊断 | `claudenovel-report` |
| 审查或改写指定单章 | `claudenovel-rewrite` |

写作不要求先跑分析、训练模型或制作标注集。新稿始终交作者审核，保留原稿和修订历史。

## 本地运行

安装插件目录内 `requirements.txt` 的依赖。将小说项目放在插件目录之外，在小说项目目录配置本地 `.env` 或环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。沿用已有供应商配置，密钥不随插件分发。

```powershell
python -X utf8 "<PLUGIN_ROOT>\agent_writer_cli.py" --project-root "<PROJECT_ROOT>" unit-run --run-id unit-01 --brief "<BRIEF_FILE>" --context-file "<CONTEXT_FILE>" --max-chars 29999
```

方案使用 UTF-8 Markdown、文本或 JSON；无前情时省略 `--context-file`。结果在小说项目的 `drafts/units/unit-01/完整单元稿.md` 与 `交稿说明.md`。

参数、恢复、作者反馈和用量边界见 [完整单元运行器](docs/UNIT_DRAFT_RUNNER.md)，逐章写作见 [逐章工作流](AGENT_WRITER.md)。机器检查通过不代表文学质量已经达到作者标准。

分析与改稿时显式提供原文和输出路径，避免把产物写入插件缓存。分析/报告命令从小说项目目录执行，以加载项目 `.env`。

## 维护

仓库根目录的 `agent_writer/`、`novel_parser/`、入口脚本和 `skills/` 是源码。修改后运行：

```powershell
python -X utf8 scripts/sync_plugin.py
python -X utf8 scripts/sync_plugin.py --check
```

第一条同步发行副本，第二条只读核对，避免插件与源码行为不一致。同步不包含密钥、小说、草稿或研究实验。不要直接在发行副本里单独修改运行代码。
