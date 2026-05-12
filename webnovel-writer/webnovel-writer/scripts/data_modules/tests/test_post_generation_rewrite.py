import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from post_generation_rewrite import build_rewrite_prompt, build_validation_payload, local_quality_checks


def test_rewrite_prompt_uses_author_settings_and_no_hidden_reference():
    prompt = build_rewrite_prompt(
        draft_text="第九章 微信到手\n\n秦思妍冷冷地看着陈默。",
        style_samples=["前文样本"],
        author_settings="秦思妍：高冷校花，陌生阶段只做有限让步。",
        target_chars="2800-3400",
    )

    assert "秦思妍：高冷校花" in prompt
    assert "第九章 微信到手" in prompt
    assert "hidden original" not in prompt.lower()
    assert "Preserve the same plot events" in prompt


def test_local_quality_checks_flags_character_breaks():
    payload = local_quality_checks("秦思妍需要你帮忙。她嘴角露出笑意。陈默拿到微信好友。")

    assert payload["contains_contact_payoff"] is True
    assert payload["qin_help_request"] is True
    assert payload["softening_counts"]["smile_arc"] == 1


def test_local_quality_checks_does_not_treat_pursuit_as_help_request():
    payload = local_quality_checks("秦思妍淡淡开口：“我加你，不代表接受你的追求。”")

    assert payload["qin_help_request"] is False


def test_local_quality_checks_flags_coercion_and_new_power_risks():
    payload = local_quality_checks("你不加我就天天堵你。系统奖励：魅力值+1，获得被动能力察言观色。")

    assert payload["chen_mo_coercion_risk"] is True
    assert payload["new_power_system_risk"] is True


def test_validation_payload_blocks_before_rewrite():
    payload = build_validation_payload("你不加我就天天堵你。系统奖励：魅力值+1。")

    assert payload["ok"] is False
    codes = {issue["code"] for issue in payload["issues"]}
    assert "missing_contact_payoff" in codes
    assert "chen_mo_coercion_risk" in codes
    assert "new_power_system_risk" in codes
