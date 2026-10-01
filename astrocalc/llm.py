"""Optional AI writer (server-side only).

The AI never calculates anything. It receives a JSON "facts" object built from the Swiss
Ephemeris chart and is asked to turn it into plain English. Its output is then checked
against the chart (see interpret.validate_claims) and rejected if it states a placement that
the calculation does not support. If no key is configured, or the call fails, callers fall back
to the deterministic template text.

Configuration (environment variables, never sent to the browser):
  ANTHROPIC_API_KEY   preferred provider
  ANTHROPIC_MODEL     optional; default tries claude-sonnet-4-5 then claude-sonnet-4-0
  OPENAI_API_KEY      used if no Anthropic key is set
  OPENAI_MODEL        optional; default gpt-4.1-mini
  AI_TIMEOUT_SECONDS  optional; default 40
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

ANTHROPIC_DEFAULT_MODELS = ["claude-sonnet-4-5", "claude-sonnet-4-0"]
OPENAI_DEFAULT_MODEL = "gpt-4.1-mini"


class AIUnavailable(Exception):
    pass


def provider() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    timeout = float(os.environ.get("AI_TIMEOUT_SECONDS", "40"))
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise AIUnavailable(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIUnavailable(f"network error: {exc}") from exc


def _anthropic(system: str, user: str, max_tokens: int) -> tuple[str, str]:
    key = os.environ["ANTHROPIC_API_KEY"]
    models = [os.environ["ANTHROPIC_MODEL"]] if os.environ.get("ANTHROPIC_MODEL") else ANTHROPIC_DEFAULT_MODELS
    last: Exception | None = None
    for model in models:
        try:
            res = _post("https://api.anthropic.com/v1/messages",
                        {"x-api-key": key, "anthropic-version": "2023-06-01"},
                        {"model": model, "max_tokens": max_tokens, "temperature": 0.4, "system": system,
                         "messages": [{"role": "user", "content": user}]})
        except AIUnavailable as exc:
            last = exc
            if "not_found" in str(exc) or "HTTP 404" in str(exc):
                continue  # model id retired/unknown -> try the next default
            raise
        text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
        return text, model
    raise AIUnavailable(str(last))


def _openai(system: str, user: str, max_tokens: int) -> tuple[str, str]:
    model = os.environ.get("OPENAI_MODEL", OPENAI_DEFAULT_MODEL)
    res = _post("https://api.openai.com/v1/chat/completions",
                {"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                {"model": model, "max_tokens": max_tokens, "temperature": 0.4,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    return res["choices"][0]["message"]["content"], model


def complete_json(system: str, user: str, max_tokens: int = 2500) -> tuple[dict[str, Any], str, str]:
    """Return (parsed_json, provider, model). Raises AIUnavailable."""
    p = provider()
    if not p:
        raise AIUnavailable("no AI key configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY)")
    text, model = (_anthropic if p == "anthropic" else _openai)(system, user, max_tokens)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIUnavailable("AI response was not JSON")
    try:
        return json.loads(m.group(0)), p, model
    except json.JSONDecodeError as exc:
        raise AIUnavailable(f"AI response was not valid JSON: {exc}") from exc
