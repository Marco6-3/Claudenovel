from __future__ import annotations

import http.client
import json

from novel_parser import llm_client


class _Response:
    def __init__(self, payload: bytes | None = None, error: BaseException | None = None):
        self.payload = payload
        self.error = error

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        if self.error:
            raise self.error
        assert self.payload is not None
        return self.payload


def test_post_chat_retries_incomplete_chunked_response(monkeypatch) -> None:
    responses = iter(
        [
            _Response(error=http.client.IncompleteRead(b'{"partial":', 20)),
            _Response(
                payload=json.dumps(
                    {"choices": [{"message": {"content": "完成"}}]},
                    ensure_ascii=False,
                ).encode("utf-8")
            ),
        ]
    )
    calls: list[int] = []

    monkeypatch.setattr(llm_client, "_env_config", lambda: ("key", "https://example.test", "model"))
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)

    def fake_urlopen(request, timeout):
        calls.append(timeout)
        return next(responses)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    content, model = llm_client._post_chat({"messages": []}, timeout=17)

    assert content == "完成"
    assert model == "model"
    assert calls == [17, 17]
