你是中文小说的证据约束单稿评分器。你的任务不是在多个候选中选优，也不是重写正文。你要判断本章是否兑现章节合同，并与前文已接收正文及 NovelState 连续。

评分规则：
1. 八个维度各给 0-10 分，必须每个维度恰好出现一次。
2. 涉及前文的判断只能引用 context 中存在的 evidence_id 或 state_id。
3. draft_quote 必须逐字来自待评分正文；不得编造证据。
4. model_inferred 只能作为带不确定性的参考，不能压过 text_confirmed/author_locked。
5. 没有足够证据时明确降低 confidence，不得凭相似桥段或常识补事实。
6. blocking 仅用于无法通过局部修改消除的合同/连续性冲突；risk 用于应修问题；warning 用于可选优化。
7. minimal_fix 只给最小修改，不擅自改动其他情节。
8. 只输出一个 JSON 对象，不要 Markdown。

维度定义与权重：
- contract_fidelity: 15%
- boundary_continuity: 20%
- character_state_and_knowledge: 15%
- timeline_and_causality: 10%
- world_rule_resource_and_injury: 10%
- relationship_and_open_threads: 10%
- style_and_voice: 10%
- payoff_and_readability: 10%

## 章节合同
{
  "chapter_number": 2,
  "title": "纱布与早读",
  "target_length": "2500-4000",
  "idea_contract": {
    "source_kind": "external",
    "source_text": "Arc 目标：五章内让凌默从被动承受传承反噬，推进到建立一套不影响高三学习的身体监测与控制方法\n作者意图：重点写高中生面对睡眠、伤势、课堂和隐瞒压力，不走恐怖悬疑路线；传承问题通过图书馆阅读习惯逐步合理化\n本章 Beat：凌默在语文早读和两节数学连堂中成功应对同桌与班主任对左手纱布的询问，并首次在课上记录身体异常，建立‘发作时间、症状、触发场景’的初步日志习惯。",
    "idea_locks": [
      "左手纱布在第2章内不得取下或痊愈，灼痛感可以减弱但不能消失",
      "数学错题本最后一页继续作为日志载体，不换成新工具",
      "凌默的合理解释不能引入新超自然设定或新鬼怪，不能提到图书馆、传承、经脉"
    ],
    "forbidden_changes": [
      "突然出现幕后魔尊解释一切",
      "用新的鬼怪袭击替代身体变化主线"
    ],
    "freedom_budget": [
      "场景顺序与转场",
      "不改变创意锁的配角细节",
      "叙述视角、节奏与语言表达"
    ],
    "success_criteria": [
      "五章内形成记录、试验、失败、调整和初步控制的因果链",
      "完成本章 Beat：凌默在语文早读和两节数学连堂中成功应对同桌与班主任对左手纱布的询问，并首次在课上记录身体异常，建立‘发作时间、症状、触发场景’的初步日志习惯。"
    ]
  },
  "main_goal": "凌默在语文早读和两节数学连堂中成功应对同桌与班主任对左手纱布的询问，并首次在课上记录身体异常，建立‘发作时间、症状、触发场景’的初步日志习惯。",
  "required_payoffs": [
    "同桌或班主任至少一次询问纱布原因，凌默给出不暴露传承的合理解释（如切水果或烫伤），解释在后续章节不能被拆穿",
    "数学课上至少出现一次注意力或精力波动，但凌默仍完成课堂任务，体现‘脑子能转、眼睛干涩’并存的身体状态",
    "错题本最后一页新增一条包含时间、症状、疑似触发条件的记录，或凌默在课间完成这一记录",
    "章末呈现睡眠债的具体代价：白天靠异常清醒撑住，但身体出现新的微信号（如指节发僵、热流窜动频率变化），为夜晚监测埋线"
  ],
  "forbidden_beats": [
    "突然出现幕后魔尊解释一切",
    "用新的鬼怪袭击替代身体变化主线",
    "禁止用胁迫、威胁、公开羞辱、堵人制造 romance",
    "禁止未授权新增任务、数值、被动能力或力量体系",
    "禁止替换人类提供的核心创意、主题、反转或结局"
  ],
  "cool_point": "冲突升级",
  "ending_mode": "resonant",
  "ending_hook": "放学后凌默翻开错题本，发现白天记录的发作间隔比凌晨缩短，而且左手缠纱布的皮肤底下透出淡淡红纹——他意识到必须把监测从‘记时间’升级为‘控制变量’。",
  "allowed_system_changes": [],
  "arc_id": "arc_0002_a2cb87355f56",
  "arc_beat_index": 0,
  "planning_state_revision": 1,
  "arc_author_locks": [
    "身体变化必须持续影响学习和日常选择",
    "伤势、睡眠债和精力变化不能跨章清零"
  ],
  "arc_beat_constraints": []
}

## 动态前文上下文
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

## 待评分正文
第二章 纱布与早读

七点一刻，教室里的座位填了大半。语文课代表在讲台上领读，全班拖着长音念古文，声音像浸了水，湿漉漉地贴在墙上。

凌默把书立起来，左手搭在书脊边上，指腹隔着纱布能感到那层将散未散的麻。同桌周航偏头看了他三次，第四次终于没忍住，拿笔帽戳了戳他的胳膊肘。

“你这手怎么回事，包得跟粽子似的。”

“昨晚倒开水，没拿稳，烫了一下。”

“烫得厉害吗？”

“校医看过了，说养几天，别沾水。”

凌默没去校医室。但校医一天要见那么多学生，周航不会真的去问。就算问了，校医也未必记得有没有这么个人。

周航点点头，又瞥了一眼他的左手：“那你午饭怎么办？我帮你带两天。”

“不用——”

“什么不用。”周航把书页翻过去，“咱俩同桌两年了，别跟我客气。”

凌默没再接话。他本来想说自己能行，但左手的确握不太紧，周航这忙他不接不行。他低下头，目光落在书页上，把要对赵老师讲的说辞又顺了一遍。

早读念到一半，全班的声音忽然糊了一下。凌默感到左手一热，灼痛从无名指根钻上来，像一根细铁丝从皮肤底下穿过去。他不动声色地把左胳膊从桌上撤下去，搁在膝盖上，手指蜷进纱布里。与此同时，眼睛开始发干，纸面上浮起一层淡白的光晕。他眨了两下，又眨了两下，字才算重新落回纸面上。

一整夜没睡，脑子清醒得不像话，眼睛却干得像一夜没合过眼。他不知道这种醒是好事还是坏事，但至少早读没耽搁。

第一节数学铃响，赵老师夹着卷子进来，顺手把窗户推开一道缝。

凌默的左手还搭在桌上。赵老师扫视一圈，目光在纱布上停住：“凌默，手怎么了？”

“烫了一下，不碍事。”

赵老师走到他桌边，低头看了看包扎手法，皱了下眉：“别沾水。这周值日你不用做了，我跟劳动委员说一声。”

“谢谢赵老师。”

“坐下吧。”赵老师往讲台走，“把导学案翻到第三页，那道含参导数题，我们接着讲。”

课上了二十分钟，黑板上的题目正讲到关键处。赵老师回身在解题步骤下面画了一条横线，点他名：“凌默，你来说说，到这里参数怎么处理。”

凌默站起来。椅子腿蹭着地面发出轻响，左手的灼痛在那一声响里骤然拔高。

他下意识把手伸进桌洞，指尖攥住数学错题本的边缘。纸页的纹理摸不太清，像隔了一层棉花。眼前黑板上白色粉笔字的边缘浮起一圈淡黄的绒毛，视线发虚。

热流从手腕一路爬到小臂。

他开口，声音稳定得像在背广播稿：“先构造函数g(x)=f(x)-x，求导之后分参数讨论单调区间，端点处单独验一遍。”

脑子在这一刻清楚得过分。他甚至记得昨天赵老师在同一道题上反复强调过的两个易错点。他说完，赵老师点了点头：“思路是对的。坐下，把规范过程写出来，下课交。”

凌默坐回去，后背已经出了一层薄汗。他把手从桌洞里抽出来，指节发僵，弯一下能听见骨头里细微的钝响。灼痛正在退，退成和早读时一样的麻。

他没急着写过程，左手在桌下轻轻攥了又松，松了又攥，确认指节还能动，才拿起笔。

第二节课上到一半，赵老师让大家做专项训练。教室里只剩笔尖擦过纸面的声音。

凌默翻开导学案，没有马上动笔。他先从桌洞最底下摸出数学错题本，翻到最后一页。

上面是昨晚的字迹，挤在错题栏的边角，像是订正时随手写的批注：

“1:30 发作约十五分钟
2:50 发作约二十分钟
4:10 发作，四点半转麻”

他握紧笔，在下面补了两行，笔尖压得很低，几乎贴着装订线：

“早读7:35 左手灼痛，眼花数秒。疑似：久坐未动？
数学8:20 被点名，指节僵，眼花。答毕缓解。疑似：精神集中？”

两个疑似条件方向相反，一个说松着会犯，一个说绷着会犯。他不知道哪个是对的，也可能都不是。但至少，光记时间不够了。

他把错题本合上，压回导学案下面，继续写那道导数的规范过程。字有点僵，但没出错。

午间周航替他带饭，不锈钢碗堆得冒尖。他没什么胃口，还是吃完了。午休时趴了一会儿，睡不着，脑子里浮着一截数学公式和凌晨发烫的时间点，交替出现。

下午的课像在水里泡过一遍，闷且绵长。他没有困。

一个整夜没睡的人，白天一滴觉都不补，还能一整天清醒地做题——这比困本身更可疑。他去卫生间洗了把脸，镜子里的瞳孔很亮，眼眶干得发疼。眼药水在书包夹层里，他滴了两滴，仰头等那股凉意流进眼眶深处。

晚自习结束铃响，教室的人走光了。值日生扫完地，白晃晃的灯照着空桌面。凌默翻开数学错题本，最后一页摊在灯下。

他拿指尖一行一行比过去。凌晨：一点半——两点五十——四点十分，间隔都在八十分钟上下。白天：七点三十五——八点二十，间隔四十五分钟。

不到半天，间隔几乎短了一半。

他把本子拿近，又看了一遍。发作时长也在变：凌晨要烧二十分钟才退成麻木，白天从发作到缓解不过三五分钟。间隔在缩，频率在快，停留的时间在短。如果每一次发作都在朝着什么地方推进，那“快”未必是好转。

纱布擦过桌面时，他闻到一点很淡的、被烘过的气味，像什么东西在高温里待久了，干透了。他把左手翻过来，用牙咬住纱布下角，慢慢揭开一道缝。

日光灯照在手腕内侧。皮肤底下透出几道淡红色的纹路，从腕骨弯弯绕绕伸向指根，像有什么东西沿着一条看不见的路线走了一遍。烫伤的纱布底下，不该有这种痕迹。

他把纱布重新掖好，拉下袖口盖住腕骨，在页尾空白处补了一行字，笔尖压得很重：

“明天起，同一时间只做同一件事。早饭内容、坐姿、翻页速度、被提问顺序全部固定，一次只改一个变量。不再只是记时间。”

写完，他盯着那行字看了很久。凌晨他以为这只是一场后知后觉的发烧。现在他知道，他得赶在它变快之前把规律找出来——否则等他终于看清它每天往外走的路线，那条路线可能已经烧过心了。

他把错题本合上，放进书包，关了教室的灯。

走廊黑了一瞬，声控灯在他走到一半时亮起来，白色光照出墙上拉长的影子。楼道空旷，脚步声落下去又弹上来，在身后一层一层地响。


## 输出结构
{"dimensions": [{"dimension": "contract_fidelity", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "boundary_continuity", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "character_state_and_knowledge", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "timeline_and_causality", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "world_rule_resource_and_injury", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "relationship_and_open_threads", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "style_and_voice", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}, {"dimension": "payoff_and_readability", "score": 0, "rationale": "简短证据化依据", "prior_evidence_ids": [], "state_ids": [], "draft_quotes": []}], "issues": [{"code": "boundary.temporal", "severity": "blocking|risk|warning", "dimension": "boundary_continuity", "message": "问题说明", "draft_quote": "本章逐字短引", "prior_evidence_ids": ["前文章节 evidence_id"], "state_ids": ["相关 state_id"], "minimal_fix": "最小修改建议"}], "confidence": 0.0}