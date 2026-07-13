from __future__ import annotations

import argparse
import json
from pathlib import Path


PLANNER_PROFILES = {
    "branch_01": (
        "规则机制分支：核心转折必须来自一个边界清楚、可被人物利用也会反噬人物的超自然规则。"
        "不能只靠战力更强或偶然救援；高潮要让规则的限制与收益同时兑现。"
    ),
    "branch_02": (
        "人物选择分支：不得用突然得到的新物品解决问题。核心转折必须由陈默主动做出的艰难选择触发，"
        "选择要保护或伤害一段具体关系，并留下不能立刻撤销的代价。"
    ),
    "branch_03": (
        "线索重构分支：不得用正面战力碾压。核心推进必须来自对可见线索、身份误判或局部世界规则的重新理解，"
        "让信息变化改变行动方案；反转必须能由切点前证据支撑。"
    ),
}


def render_prompt(case_id: str, branch_id: str, public_prompt: str, contract: dict) -> str:
    profile = PLANNER_PROFILES[branch_id]
    return (
        "# Branch-first 剧情卡规划任务\n\n"
        "你是隔离的剧情 Planner，不是正文 Writer。不得搜索或读取原小说目标章、private、gold、"
        "其他分支卡、既有候选、评审或映射。只可使用下方公开任务书。\n\n"
        "外部创意、创意锁和禁改项拥有最高优先级。你的职责是在 freedom budget 内提出一条可独立扩写的剧情机制，"
        "不是替换人的想法。不得写正文、对白段落或成品章节。\n\n"
        "## 本分支的互补职责\n\n"
        f"{profile}\n\n"
        "## Branch Card 要求\n\n"
        "- `core_mechanism` 必须描述因果机制，不能写成‘更重人物/更有悬念’一类风格标签。\n"
        "- 五个 beats 必须形成建立、升级、不可逆选择、局部兑现、尾钩。\n"
        "- `real_cost` 必须在本单元真实发生，不能只是‘可能有危险’。\n"
        "- `idea_lock_evidence` 逐条说明公开创意锁落在哪个 beat。\n"
        "- 不新增未授权核心设定；需要新鬼物或小道具时，只能作为自由预算内的局部实现。\n"
        "- 只输出一个严格 JSON 对象，不要 Markdown 代码围栏。\n\n"
        "JSON 字段固定为：schema_version、case_id、branch_id、core_mechanism、premise_difference、"
        "character_choice、real_cost、world_rule_usage、beats（setup、escalation、irreversible_choice、"
        "local_payoff、end_hook）、freedom_budget_choices、idea_lock_evidence、forbidden_change_checks、risk_register。\n\n"
        "类型约定：world_rule_usage 用对象描述规则/限制/后果；freedom_budget_choices 用对象把公开自由维度映射到本分支选择；"
        "idea_lock_evidence 用对象把每条创意锁原文映射到 beat；forbidden_change_checks 用对象把每条禁改项原文映射到规避方式；"
        "risk_register 是 1–3 个字符串的数组。\n\n"
        "固定值：\n"
        f"- schema_version: branch-card/v1\n- case_id: {case_id}\n- branch_id: {branch_id}\n\n"
        "## 公开 IdeaContract\n\n"
        f"{json.dumps(contract, ensure_ascii=False, indent=2)}\n\n"
        "## 公开写作任务书与切点原文\n\n"
        f"{public_prompt}\n"
    )


def prepare(public_run: Path, out_dir: Path, case_ids: list[str]) -> list[str]:
    written: list[str] = []
    for case_id in case_ids:
        public_dir = public_run / case_id / "public"
        prompt_path = public_dir / "writer_prompt.md"
        contract_path = public_dir / "idea_contract.json"
        if not prompt_path.is_file() or not contract_path.is_file():
            raise FileNotFoundError(f"missing public benchmark inputs for {case_id}")
        public_prompt = prompt_path.read_text(encoding="utf-8")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        for branch_id in PLANNER_PROFILES:
            target = out_dir / case_id / "planner_prompts" / f"{branch_id}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_prompt(case_id, branch_id, public_prompt, contract), encoding="utf-8")
            written.append(str(target))
    manifest = out_dir / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"planner_prompts": written}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare isolated Branch Card planner prompts")
    parser.add_argument("--public-run", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args(argv)
    written = prepare(args.public_run, args.out_dir, args.case)
    print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
