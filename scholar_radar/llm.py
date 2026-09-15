"""Small, dependency-free clients for free-tier LLM APIs that return JSON.

Supported: Google Gemini (default, free tier) and any OpenAI-compatible API
(Groq, OpenRouter). Pick with LLM_PROVIDER or just set one API key.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from .config import env

log = logging.getLogger(__name__)

GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_MODEL = "gemini-flash-latest"


class LLMError(RuntimeError):
    pass


def parse_json_text(text: str) -> dict[str, Any]:
    """Parse model output that should be JSON, tolerating ```json fences and stray prose."""
    cleaned = re.sub(r"^\s*```(?:json)?|```\s*$", "", (text or "").strip(), flags=re.MULTILINE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise LLMError(f"Model did not return JSON: {text[:200]!r}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise LLMError("Expected a JSON object")
    return value


class BaseLLM:
    name = "base"

    def __init__(self, model: str, min_interval: float) -> None:
        self.model = model
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            self._throttle()
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=120)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise LLMError(f"{self.name} request failed: {exc}") from exc
                time.sleep(10 * (attempt + 1))
                continue
            if resp.status_code == 200:
                self.calls += 1
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry_after = resp.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else 20 * (attempt + 1)
                log.warning("%s HTTP %s - retrying in %ss", self.name, resp.status_code, delay)
                time.sleep(delay)
                continue
            raise LLMError(f"{self.name} HTTP {resp.status_code}: {resp.text[:300]}")
        raise LLMError(f"{self.name}: retries exhausted")

    def complete_json(self, system: str, prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class GeminiLLM(BaseLLM):
    name = "gemini"

    def __init__(self, api_key: str, model: str, min_interval: float) -> None:
        super().__init__(model, min_interval)
        self.api_key = api_key

    def _generate(self, model: str, system: str, prompt: str) -> dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        return self._post(url, {"x-goog-api-key": self.api_key}, body)

    def complete_json(self, system: str, prompt: str) -> dict[str, Any]:
        try:
            data = self._generate(self.model, system, prompt)
        except LLMError as exc:
            if "HTTP 404" in str(exc) and self.model != GEMINI_FALLBACK_MODEL:
                log.warning("Model %s not found, switching to %s", self.model, GEMINI_FALLBACK_MODEL)
                self.model = GEMINI_FALLBACK_MODEL
                data = self._generate(self.model, system, prompt)
            else:
                raise
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response: {str(data)[:300]}") from exc
        return parse_json_text("".join(p.get("text", "") for p in parts))


class OpenAICompatibleLLM(BaseLLM):
    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 min_interval: float) -> None:
        super().__init__(model, min_interval)
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete_json(self, system: str, prompt: str) -> dict[str, Any]:
        body = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        }
        data = self._post(f"{self.base_url}/chat/completions",
                          {"Authorization": f"Bearer {self.api_key}"}, body)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected {self.name} response: {str(data)[:300]}") from exc
        return parse_json_text(content)


def get_llm() -> BaseLLM | None:
    """Build the configured LLM client, or None for keyword-only mode."""
    provider = (env("LLM_PROVIDER") or "").lower()
    interval = float(env("LLM_MIN_INTERVAL_SECONDS", "7") or 7)

    if provider == "none":
        return None
    if provider in ("", "gemini") and env("GEMINI_API_KEY"):
        return GeminiLLM(env("GEMINI_API_KEY"), env("GEMINI_MODEL", GEMINI_DEFAULT_MODEL), interval)
    if provider in ("", "groq") and env("GROQ_API_KEY"):
        return OpenAICompatibleLLM("groq", "https://api.groq.com/openai/v1", env("GROQ_API_KEY"),
                                   env("GROQ_MODEL", "llama-3.3-70b-versatile"), interval)
    if provider in ("", "openrouter") and env("OPENROUTER_API_KEY"):
        model = env("OPENROUTER_MODEL")
        if not model:
            raise LLMError("Set OPENROUTER_MODEL (pick a free model on openrouter.ai/models)")
        return OpenAICompatibleLLM("openrouter", "https://openrouter.ai/api/v1",
                                   env("OPENROUTER_API_KEY"), model, interval)
    if provider:
        raise LLMError(f"LLM_PROVIDER={provider} but its API key is not set")
    return None
