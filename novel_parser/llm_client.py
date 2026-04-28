"""OpenAI-compatible LLM client for editorial chapter reports."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any, Dict, Tuple

from .evaluator import QualityReport


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class LLMConfigError(RuntimeError):
    """Raised when LLM configuration is missing or invalid."""


def _env_config() -> Tuple[str, str, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigError("未配置 OPENAI_API_KEY，已跳过 LLM 编辑诊断。")
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
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
- 不要声称你已经阅读全书全文。
- 如果 chapter_text_is_excerpt 为 true，要明确说明正文只送入了摘录。
- 不要续写完整正文，只给编辑诊断和后续剧情方向。
- 输出简体中文 Markdown。

必须包含以下小节：
1. 总体判断
2. 剧情质量
3. 文笔质量
4. 最大问题
5. 可保留优点
6. 后续剧情走向（给 3 条，每条包含冲突核心、人物推进、下一章钩子）

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


def generate_editorial_report(
    report: QualityReport,
    chapter_text: str,
    chapter_title: str,
    max_chars: int = 12000,
) -> Tuple[str, bool, str]:
    """Call an OpenAI-compatible chat completions endpoint."""
    api_key, base_url, model = _env_config()
    prompt, truncated = build_editorial_prompt(report, chapter_text, chapter_title, max_chars)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是严谨的中文网络小说编辑，输出必须具体、可执行、基于证据。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM 请求失败：HTTP {exc.code} {body[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 请求失败：{exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常：{json.dumps(data, ensure_ascii=False)[:800]}") from exc
    return content.strip(), truncated, model
