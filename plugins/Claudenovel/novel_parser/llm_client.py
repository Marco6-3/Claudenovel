"""OpenAI-compatible LLM client for editorial and evidence-grounded reports."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .evaluator import QualityReport


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


class LLMConfigError(RuntimeError):
    """Raised when LLM configuration is missing or invalid."""


def load_dotenv(start: Path | None = None) -> None:
    """Load simple KEY=VALUE entries from the nearest .env file."""
    current = (start or Path.cwd()).resolve()
    for folder in [current, *current.parents]:
        env_path = folder / ".env"
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return


def _env_config() -> Tuple[str, str, str]:
    load_dotenv()
    api_key = (
        os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        raise LLMConfigError("未配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY，已跳过 LLM 分析。")
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("DEEPSEEK_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or DEFAULT_MODEL
    )
    return api_key, base_url, model


def excerpt_text(text: str, max_chars: int) -> Tuple[str, bool]:
    """Return full text or an opening/middle/ending excerpt within max_chars."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False

    middle_marker = "\n\n[中间摘录]\n\n"
    ending_marker = "\n\n[结尾摘录]\n\n"
    marker_chars = len(middle_marker) + len(ending_marker)
    part = max(1, (max_chars - marker_chars) // 3)
    mid_start = max(0, len(text) // 2 - part // 2)
    mid_end = min(len(text), mid_start + part)
    excerpt = (
        text[:part]
        + middle_marker
        + text[mid_start:mid_end]
        + ending_marker
        + text[-part:]
    )
    return excerpt[:max_chars], True


def build_editorial_prompt(
    report: QualityReport,
    chapter_text: str,
    chapter_title: str,
    max_chars: int,
) -> Tuple[str, bool]:
    text_for_llm, truncated = excerpt_text(chapter_text, max_chars)
    metrics: Dict[str, Any] = {
        "scores": {
            "plot_score": report.plot_score,
            "prose_score": report.prose_score,
            "hook_score": report.hook_score,
        },
        "metrics": asdict(report.metrics),
        "percentiles": report.percentiles,
        "strengths": report.strengths,
        "weaknesses": report.weaknesses,
        "rule_recommendations": report.recommendations,
        "similar_chapters": [
            {"index": idx, "title": title, "similarity": sim}
            for idx, title, sim in report.similar_chapters
        ],
        "chapter_text_is_excerpt": truncated,
    }
    prompt = f"""你是一名网络小说编辑，只能基于下面给出的结构化指标、相似章节信息和用户输入章节进行判断。
限制：
- 不要声称你已经阅读全文，除非正文完整给出。
- 如果 chapter_text_is_excerpt 为 true，要明确说明正文只送入了摘录。
- 不要续写完整正文，只给当前单元的编辑诊断和修订方案。
- 输出简体中文 Markdown。

必须包含以下小节：
1. 总体判断
2. 剧情质量
3. 文笔质量
4. 最大问题
5. 可保留优点
6. 当前单元修订方案：给 3 条，每条包含冲突核心、人物行动、局部结尾

章节标题：{chapter_title}

本地结构化指标 JSON：
```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

用户输入章节：
```text
{text_for_llm}
```
"""
    return prompt, truncated


def _post_chat(payload: Dict[str, Any], timeout: int = 600) -> Tuple[str, str]:
    api_key, base_url, model = _env_config()
    payload = {**payload, "model": model}
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM 请求失败：HTTP {exc.code} {body[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 请求失败：{exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常：{json.dumps(data, ensure_ascii=False)[:1200]}") from exc
    return content.strip(), model


def generate_editorial_report(
    report: QualityReport,
    chapter_text: str,
    chapter_title: str,
    max_chars: int = 12000,
) -> Tuple[str, bool, str]:
    """Call an OpenAI-compatible chat completions endpoint."""
    prompt, truncated = build_editorial_prompt(report, chapter_text, chapter_title, max_chars)
    content, model = _post_chat(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的中文网络小说编辑，输出必须具体、可执行、基于证据。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "reasoning_effort": "high",
            "thinking": {"type": "enabled"},
        },
        timeout=600,
    )
    return content, truncated, model


def call_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.4,
    timeout: int = 600,
) -> Tuple[str, str]:
    """Generic chat completion call. Returns (content, model)."""
    content, model = _post_chat(
        {
            "messages": messages,
            "temperature": temperature,
        },
        timeout=timeout,
    )
    return content, model


def call_direct_analysis(
    messages: List[Dict[str, str]],
    temperature: float = 0.5,
    timeout: int = 600,
) -> Tuple[str, str]:
    """Chat call for direct (no-structure) LLM analysis. Higher temperature for free-form discovery."""
    return call_chat(messages, temperature=temperature, timeout=timeout)


def call_hybrid_analysis(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    timeout: int = 600,
) -> Tuple[str, str]:
    """Chat call for hybrid (structured + LLM) analysis. Lower temperature for grounded judgment."""
    return call_chat(messages, temperature=temperature, timeout=timeout)


def generate_context_report(prompt_text: str) -> Tuple[str, str]:
    """Call the configured LLM with a prebuilt evidence-grounded prompt."""
    return _post_chat(
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的中文网络小说编辑。必须严格基于用户给出的证据编号分析，"
                        "每个关键判断都要引用证据编号；证据不足时直接说明。"
                    ),
                },
                {"role": "user", "content": prompt_text},
            ],
            "temperature": 0.35,
            "reasoning_effort": "high",
            "thinking": {"type": "enabled"},
        },
        timeout=600,
    )
