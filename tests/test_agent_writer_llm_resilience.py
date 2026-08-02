from __future__ import annotations

from agent_writer.llm_client import LLMConfig, OpenAICompatibleClient


def test_truncated_thinking_response_retries_with_larger_output_budget(monkeypatch) -> None:
    client = OpenAICompatibleClient(
        LLMConfig(
            base_url="https://example.test/v1",
            model="reasoning-model",
            api_key="test-key",
            thinking="enabled",
        )
    )
    budgets: list[int] = []

    def fake_post(url, payload, *, max_attempts):
        budgets.append(payload["max_tokens"])
        if len(budgets) == 1:
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "", "reasoning_content": "内部推理" * 100},
                    }
                ]
            }
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"ok":true}', "reasoning_content": "完成"},
                }
            ]
        }

    monkeypatch.setattr(client, "_post_json", fake_post)

    content = client.complete("test", max_tokens=1000, max_token_ceiling=4000)

    assert content == '{"ok":true}'
    assert budgets == [1000, 2000]


def test_structured_request_uses_official_json_mode_and_disables_thinking(monkeypatch) -> None:
    client = OpenAICompatibleClient(
        LLMConfig(
            base_url="https://example.test/v1",
            model="deepseek-v4-flash",
            api_key="test-key",
            thinking="disabled",
            response_format="json_object",
        )
    )
    payloads: list[dict] = []

    def fake_post(url, payload, *, max_attempts):
        payloads.append(payload)
        return {
            "choices": [
                {"finish_reason": "stop", "message": {"content": '{"ok":true}'}},
            ]
        }

    monkeypatch.setattr(client, "_post_json", fake_post)

    assert client.complete("请输出 JSON", temperature=0.2) == '{"ok":true}'
    assert payloads[0]["thinking"] == {"type": "disabled"}
    assert payloads[0]["response_format"] == {"type": "json_object"}
    assert payloads[0]["temperature"] == 0.2


def test_thinking_request_omits_ineffective_temperature(monkeypatch) -> None:
    client = OpenAICompatibleClient(
        LLMConfig(
            base_url="https://example.test/v1",
            model="deepseek-v4-pro",
            api_key="test-key",
            thinking="enabled",
        )
    )
    payloads: list[dict] = []

    def fake_post(url, payload, *, max_attempts):
        payloads.append(payload)
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "完成", "reasoning_content": "推理"},
                }
            ]
        }

    monkeypatch.setattr(client, "_post_json", fake_post)

    assert client.complete("test", temperature=0.9) == "完成"
    assert payloads[0]["thinking"] == {"type": "enabled"}
    assert "temperature" not in payloads[0]


def test_empty_json_content_retries_without_inflating_token_budget(monkeypatch) -> None:
    client = OpenAICompatibleClient(
        LLMConfig(
            base_url="https://example.test/v1",
            model="deepseek-v4-flash",
            api_key="test-key",
            response_format="json_object",
        )
    )
    payloads: list[dict] = []

    def fake_post(url, payload, *, max_attempts):
        payloads.append(payload)
        content = "" if len(payloads) == 1 else '{"ok":true}'
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)

    assert client.complete("请输出 JSON", max_tokens=6000) == '{"ok":true}'
    assert [payload["max_tokens"] for payload in payloads] == [6000, 6000]
    assert "空 content" in payloads[1]["messages"][1]["content"]
