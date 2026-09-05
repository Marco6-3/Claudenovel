import json
from contextlib import contextmanager

from novel_parser import llm_client


def test_legacy_writer_uses_kimi_payload(monkeypatch):
    monkeypatch.setattr(llm_client, "_env_config", lambda: ("key", "https://example.test/v1", "kimi-k3"))
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    seen = []

    @contextmanager
    def post(request, timeout):
        seen.append(json.loads(request.data))

        class Response:
            def read(self):
                return b'{"choices":[{"message":{"content":"ok"}}]}'

        yield Response()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", post)
    assert llm_client._post_chat({"messages": [], "temperature": 0.7, "max_tokens": 200, "thinking": {"type": "disabled"}})[0] == "ok"
    assert seen[0]["max_completion_tokens"] == 200
    assert seen[0]["reasoning_effort"] == "low"
    assert not {"temperature", "thinking", "max_tokens"} & seen[0].keys()
