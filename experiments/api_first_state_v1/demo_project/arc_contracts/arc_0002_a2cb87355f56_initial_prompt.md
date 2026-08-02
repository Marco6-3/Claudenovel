你是中文商业小说的滚动时域 Arc Planner。你只规划未来章节，不写正文。
一次规划 N 章，但生产系统随后只激活和生成第一章；每接收一章后，剩余计划会基于新状态重排。

硬规则：
1. author_intent 与 author_locks 是最高真源，不得替换、弱化或制造相反反转。
2. 每章必须有局部建立、推进和兑现，不能把本章 required_payoffs 推给下一章。
3. 计划必须承接 context 的伤势、睡眠、资源、人物知识、关系和 open threads。
4. 不新增 forbidden_changes 中的内容；不擅自增加力量规则或核心身份反转。
5. relevant_threads 只能填写 context 中真实存在的 state_id，不确定时留空。
6. 只输出 JSON 对象，不要正文或解释。

start_chapter=2
horizon=5
objective=五章内让凌默从被动承受传承反噬，推进到建立一套不影响高三学习的身体监测与控制方法
author_intent=重点写高中生面对睡眠、伤势、课堂和隐瞒压力，不走恐怖悬疑路线；传承问题通过图书馆阅读习惯逐步合理化
author_locks=["身体变化必须持续影响学习和日常选择", "伤势、睡眠债和精力变化不能跨章清零"]
forbidden_changes=["突然出现幕后魔尊解释一切", "用新的鬼怪袭击替代身体变化主线"]
success_criteria=["五章内形成记录、试验、失败、调整和初步控制的因果链"]

## 动态上下文
{
  "schema_version": "chapter-context/v1",
  "chapter_number": 2,
  "state_revision": 1,
  "state_synced_through_chapter": 1,
  "state_is_stale": false,
  "recent_chapters": [
    {
      "chapter_number": 1,
      "file": "C:\\Users\\mingzhe Liu\\OneDrive\\Desktop\\Claudenovel\\experiments\\api_first_state_v1\\demo_project\\accepted\\chapter_0001.md",
      "sha256": "0b8b739f2cea064bb92ec77d0cfb3266f60b5d319df7232de16d7365adcfc9a9",
      "text": "凌晨四点以后，凌默左手的灼痛才慢慢退成麻木。传承留下的热流仍在经脉里乱窜，他不敢继续引气，只把每次发作的时间记在数学错题本最后一页。\n\n六点四十五分，他用纱布包扎左手，套上校服。昨夜没有睡，但身体反常地清醒；脑子能转，眼睛却又干又涩。\n\n七点整，他带着伤走进教室。第一节是语文早读，上午还有两节数学连堂，他必须先想好怎样向同桌和班主任解释手上的纱布。\n",
      "evidence": [
        {
          "evidence_id": "novel-5b4f5b9dd99f:CH0001-P001",
          "chapter_number": 1,
          "paragraph_index": 1,
          "text": "凌晨四点以后，凌默左手的灼痛才慢慢退成麻木。传承留下的热流仍在经脉里乱窜，他不敢继续引气，只把每次发作的时间记在数学错题本最后一页。",
          "paragraph_sha256": "a73e3f57489ce049d813543d6fef23413e33a725929f3b81fe1e97767db1e272"
        },
        {
          "evidence_id": "novel-5b4f5b9dd99f:CH0001-P002",
          "chapter_number": 1,
          "paragraph_index": 2,
          "text": "六点四十五分，他用纱布包扎左手，套上校服。昨夜没有睡，但身体反常地清醒；脑子能转，眼睛却又干又涩。",
          "paragraph_sha256": "9e2b3b0b099162749aded1be443ee22f14198dfaaa2dacecff76565394b48af3"
        },
        {
          "evidence_id": "novel-5b4f5b9dd99f:CH0001-P003",
          "chapter_number": 1,
          "paragraph_index": 3,
          "text": "七点整，他带着伤走进教室。第一节是语文早读，上午还有两节数学连堂，他必须先想好怎样向同桌和班主任解释手上的纱布。",
          "paragraph_sha256": "4f966437b5e410c0d0df67e4025b34220b4b111645304207ec13e5568e357116"
        }
      ]
    }
  ],
  "selected_state": [
    {
      "layer": "authority_layer",
      "record": {
        "state_id": "author.project_premise",
        "subject": "滚动状态闭环演示",
        "claim": "项目核心前提",
        "value": "高中生凌默在高三学业压力中学习控制图书馆传承造成的身体变化",
        "authority": "author_locked",
        "status": "active",
        "confidence": 1.0,
        "evidence_refs": [],
        "introduced_chapter": 0,
        "updated_chapter": 0,
        "tags": [
          "project",
          "premise"
        ],
        "author_note": "项目初始化时由作者输入，模型不得覆盖。",
        "supersedes": []
      },
      "selection_reason": "author_locked"
    },
    {
      "layer": "entity_states",
      "record": {
        "state_id": "entity.lingmo.inherited_heat_state",
        "subject": "凌默",
        "claim": "凌默体内有传承留下的热流在经脉中乱窜，且左手出现灼痛发作",
        "value": "凌晨四点以后左手灼痛才慢慢退成麻木；传承留下的热流仍在经脉里乱窜；他不敢继续引气；每次发作时间记在数学错题本最后一页",
        "authority": "text_confirmed",
        "status": "active",
        "confidence": 1.0,
        "evidence_refs": [
          {
            "evidence_id": "novel-5b4f5b9dd99f:CH0001-P001",
            "chapter_number": 1,
            "paragraph_index": 1,
            "paragraph_sha256": "a73e3f57489ce049d813543d6fef23413e33a725929f3b81fe1e97767db1e272",
            "quote": "凌晨四点以后，凌默左手的灼痛才慢慢退成麻木。传承留下的热流仍在经脉里乱窜，他不敢继续引气，只把每次发作的时间记在数学错题本最后一页。"
          }
        ],
        "introduced_chapter": 1,
        "updated_chapter": 1,
        "tags": [
          "inheritance",
          "body_change",
          "left_hand",
          "meridians",
          "episode_log"
        ],
        "author_note": "",
        "supersedes": []
      },
      "selection_reason": "recent_state_change"
    },
    {
      "layer": "entity_states",
      "record": {
        "state_id": "entity.lingmo.left_hand_bandaged",
        "subject": "凌默",
        "claim": "凌默左手用纱布包扎，带着伤到校",
        "value": "六点四十五分用纱布包扎左手；七点整带着伤走进教室",
        "authority": "text_confirmed",
        "status": "active",
        "confidence": 1.0,
        "evidence_refs": [
          {
            "evidence_id": "novel-5b4f5b9dd99f:CH0001-P002",
            "chapter_number": 1,
            "paragraph_index": 2,
            "paragraph_sha256": "9e2b3b0b099162749aded1be443ee22f14198dfaaa2dacecff76565394b48af3",
            "quote": "六点四十五分，他用纱布包扎左手，套上校服。"
          },
          {
            "evidence_id": "novel-5b4f5b9dd99f:CH0001-P003",
            "chapter_number": 1,
            "paragraph_index": 3,
            "paragraph_sha256": "4f966437b5e410c0d0df67e4025b34220b4b111645304207ec13e5568e357116",
            "quote": "七点整，他带着伤走进教室。"
          }
        ],
        "introduced_chapter": 1,
        "updated_chapter": 1,
        "tags": [
          "left_hand",
          "bandage",
          "injury",
          "school"
        ],
        "author_note": "",
        "supersedes": []
      },
      "selection_reason": "recent_state_change"
    },
    {
      "layer": "open_threads",
      "record": {
        "state_id": "open.lingmo.explain_bandage",
        "subject": "凌默",
        "claim": "凌默尚未想好如何向同桌和班主任解释手上的纱布",
        "value": "他必须先想好怎样向同桌和班主任解释手上的纱布",
        "authority": "text_confirmed",
        "status": "active",
        "confidence": 1.0,
        "evidence_refs": [
          {
            "evidence_id": "novel-5b4f5b9dd99f:CH0001-P003",
            "chapter_number": 1,
            "paragraph_index": 3,
            "paragraph_sha256": "4f966437b5e410c0d0df67e4025b34220b4b111645304207ec13e5568e357116",
            "quote": "第一节是语文早读，上午还有两节数学连堂，他必须先想好怎样向同桌和班主任解释手上的纱布。"
          }
        ],
        "introduced_chapter": 1,
        "updated_chapter": 1,
        "tags": [
          "school",
          "explanation",
          "deskmate",
          "homeroom_teacher"
        ],
        "author_note": "",
        "supersedes": []
      },
      "selection_reason": "open_thread"
    }
  ],
  "omitted_model_proposals": 0,
  "requested_entities": [],
  "requested_threads": [],
  "approximate_chars": 2749,
  "budget_chars": 24000
}

## 输出结构
{"beats": [{"chapter_number": 2, "title": "章名", "goal": "本章发生且可验证的目标", "required_payoffs": ["本章必须兑现的事件"], "ending_hook": "完成局部弧后的章尾增量", "focus_entities": ["角色名"], "relevant_threads": ["已有 state_id；没有则留空"], "must_preserve": ["不能漂移的本章约束"], "risk_checks": ["连续性风险"]}, {"chapter_number": 3, "title": "章名", "goal": "本章发生且可验证的目标", "required_payoffs": ["本章必须兑现的事件"], "ending_hook": "完成局部弧后的章尾增量", "focus_entities": ["角色名"], "relevant_threads": ["已有 state_id；没有则留空"], "must_preserve": ["不能漂移的本章约束"], "risk_checks": ["连续性风险"]}, {"chapter_number": 4, "title": "章名", "goal": "本章发生且可验证的目标", "required_payoffs": ["本章必须兑现的事件"], "ending_hook": "完成局部弧后的章尾增量", "focus_entities": ["角色名"], "relevant_threads": ["已有 state_id；没有则留空"], "must_preserve": ["不能漂移的本章约束"], "risk_checks": ["连续性风险"]}, {"chapter_number": 5, "title": "章名", "goal": "本章发生且可验证的目标", "required_payoffs": ["本章必须兑现的事件"], "ending_hook": "完成局部弧后的章尾增量", "focus_entities": ["角色名"], "relevant_threads": ["已有 state_id；没有则留空"], "must_preserve": ["不能漂移的本章约束"], "risk_checks": ["连续性风险"]}, {"chapter_number": 6, "title": "章名", "goal": "本章发生且可验证的目标", "required_payoffs": ["本章必须兑现的事件"], "ending_hook": "完成局部弧后的章尾增量", "focus_entities": ["角色名"], "relevant_threads": ["已有 state_id；没有则留空"], "must_preserve": ["不能漂移的本章约束"], "risk_checks": ["连续性风险"]}]}