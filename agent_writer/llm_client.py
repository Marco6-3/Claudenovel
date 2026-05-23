from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env import first_env, load_env


class LLMConfigError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int = 120

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "LLMConfig":
        load_env(project_root)
        base_url = first_env("LLM_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL", default="")
        model = first_env("LLM_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL", default="")
        api_key = first_env("LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", default="")
        timeout_raw = first_env("LLM_TIMEOUT", default="120")
        if not base_url:
            raise LLMConfigError("missing LLM_BASE_URL or OPENAI_BASE_URL")
        if not model:
            raise LLMConfigError("missing LLM_MODEL or OPENAI_MODEL")
        if not api_key:
            raise LLMConfigError("missing LLM_API_KEY or OPENAI_API_KEY")
        try:
            timeout = int(timeout_raw)
        except ValueError:
            timeout = 120
        return cls(base_url=base_url.rstrip("/"), model=model, api_key=api_key, timeout=timeout)

    @property
    def chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def complete(
        self,
        prompt: str,
        *,
        system: str = "你是一个严格遵守章节合同的中文网文写作 agent。",
        temperature: float = 0.7,
        max_tokens: int = 2200,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post_json(self.config.chat_url, payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError("LLM response did not contain choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMRequestError("LLM response content is empty")
        return content.strip()

    def smoke(self) -> dict[str, Any]:
        text = self.complete(
            "请只回复两个汉字：可用",
            system="你只做连通性测试。",
            temperature=0,
            max_tokens=16,
        )
        return {"model": self.config.model, "ok": bool(text.strip()), "sample_chars": len(text)}

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise LLMRequestError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMRequestError(f"LLM request failed: {exc.reason}") from exc
        return json.loads(text)


def build_client(project_root: Path | None = None) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(LLMConfig.from_env(project_root))
