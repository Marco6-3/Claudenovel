from __future__ import annotations

import json
import http.client
import os
import socket
import time
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
    thinking: str = "omit"
    response_format: str = "text"

    @classmethod
    def from_env(cls, project_root: Path | None = None, *, role: str | None = None) -> "LLMConfig":
        load_env(project_root)
        role_prefix = role.strip().upper() if role else ""
        base_names = ["LLM_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL"]
        model_names = ["LLM_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL"]
        key_names = ["LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"]
        timeout_names = ["LLM_TIMEOUT"]
        thinking_names = ["LLM_THINKING"]
        response_format_names = ["LLM_RESPONSE_FORMAT"]
        if role_prefix:
            base_names.insert(0, f"{role_prefix}_BASE_URL")
            model_names.insert(0, f"{role_prefix}_MODEL")
            key_names.insert(0, f"{role_prefix}_API_KEY")
            timeout_names.insert(0, f"{role_prefix}_TIMEOUT")
            thinking_names.insert(0, f"{role_prefix}_THINKING")
            response_format_names.insert(0, f"{role_prefix}_RESPONSE_FORMAT")
        base_url = first_env(*base_names, default="")
        model = first_env(*model_names, default="")
        api_key = first_env(*key_names, default="")
        timeout_raw = first_env(*timeout_names, default="120")
        default_thinking = "disabled" if "deepseek.com" in base_url.lower() else "omit"
        thinking = first_env(*thinking_names, default=default_thinking).strip().lower()
        structured_roles = {"STATE", "SCORER", "PLANNER", "JUDGE"}
        default_response_format = "json_object" if role_prefix in structured_roles else "text"
        response_format = first_env(
            *response_format_names,
            default=default_response_format,
        ).strip().lower()
        if response_format == "json":
            response_format = "json_object"
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
        if thinking not in {"enabled", "disabled", "omit"}:
            raise LLMConfigError("LLM_THINKING must be enabled, disabled, or omit")
        if response_format not in {"text", "json_object"}:
            raise LLMConfigError("LLM_RESPONSE_FORMAT must be text or json_object")
        return cls(
            base_url=base_url.rstrip("/"),
            model=model,
            api_key=api_key,
            timeout=timeout,
            thinking=thinking,
            response_format=response_format,
        )

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
        max_attempts: int = 3,
        max_truncation_retries: int = 2,
        max_token_ceiling: int = 32768,
        max_empty_retries: int = 1,
    ) -> str:
        token_budget = max(1, int(max_tokens))
        token_ceiling = max(token_budget, int(max_token_ceiling))
        truncation_retries = 0
        empty_retries = 0
        request_prompt = prompt
        while True:
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": request_prompt},
                ],
                "max_tokens": token_budget,
            }
            if self.config.thinking != "omit":
                payload["thinking"] = {"type": self.config.thinking}
            if self.config.thinking == "disabled":
                payload["temperature"] = temperature
            if self.config.response_format == "json_object":
                payload["response_format"] = {"type": "json_object"}
            data = self._post_json(
                self.config.chat_url,
                payload,
                max_attempts=max_attempts,
            )
            try:
                choice = data["choices"][0]
                message = choice["message"]
                content = message.get("content")
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMRequestError("LLM response did not contain choices[0].message") from exc
            finish_reason = str(choice.get("finish_reason") or "")
            reasoning_characters = len(str(message.get("reasoning_content") or ""))
            output_starved = finish_reason == "length"
            can_retry = (
                output_starved
                and truncation_retries < max(0, max_truncation_retries)
                and token_budget < token_ceiling
            )
            if can_retry:
                token_budget = min(token_budget * 2, token_ceiling)
                truncation_retries += 1
                continue
            if output_starved:
                raise LLMRequestError(
                    "LLM exhausted output budget "
                    f"(max_tokens={token_budget}, finish_reason={finish_reason}, "
                    f"reasoning_characters={reasoning_characters})"
                )
            if not isinstance(content, str) or not content.strip():
                if empty_retries < max(0, max_empty_retries):
                    empty_retries += 1
                    if self.config.response_format == "json_object":
                        request_prompt = (
                            prompt
                            + "\n\n上一次接口返回了空 content。请现在只输出一个完整、非空的 JSON 对象。"
                        )
                    continue
                raise LLMRequestError(
                    "LLM response content is empty "
                    f"(finish_reason={finish_reason}, reasoning_characters={reasoning_characters})"
                )
            return content.strip()

    def smoke(self) -> dict[str, Any]:
        text = self.complete(
            "请只回复两个汉字：可用",
            system="你只做连通性测试。",
            temperature=0,
            max_tokens=256,
        )
        return {"model": self.config.model, "ok": bool(text.strip()), "sample_chars": len(text)}

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        attempts = max(1, int(max_attempts))
        for attempt in range(1, attempts + 1):
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
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise LLMRequestError("LLM response JSON must be an object")
                return payload
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt >= attempts:
                    raise LLMRequestError(f"LLM HTTP {exc.code}: {detail}") from exc
            except (
                urllib.error.URLError,
                http.client.IncompleteRead,
                json.JSONDecodeError,
                TimeoutError,
                socket.timeout,
            ) as exc:
                if attempt >= attempts:
                    detail = getattr(exc, "reason", str(exc))
                    raise LLMRequestError(
                        f"LLM request failed after {attempts} attempts: {detail}"
                    ) from exc
            time.sleep(min(2 ** (attempt - 1), 4))
        raise LLMRequestError("LLM returned no response")


def build_client(project_root: Path | None = None, *, role: str | None = None) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(LLMConfig.from_env(project_root, role=role))
