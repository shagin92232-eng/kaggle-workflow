"""LLM client — OpenRouter with Gemini fallback; retries, backoff, JSON mode."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Google AI Studio exposes an OpenAI-compatible endpoint — same payload shape
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MAX_RETRIES = 4


class LLMError(RuntimeError):
    pass


class PermanentLLMError(LLMError):
    """4xx errors (bad key, no credit, unknown model) — retrying cannot help."""


# Index of the first known-working model in the fallback list, so a dead
# model isn't re-tried on every single call once we've fallen past it.
_model_index = 0


async def chat(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """Single-turn chat completion. Returns assistant text.

    OPENROUTER_MODEL may be a comma-separated list; on a permanent error
    (model removed, free tier gone) the next model in the list is tried.
    If every OpenRouter model fails and GEMINI_API_KEY is set, Gemini
    (Google AI Studio) is used as the final fallback.
    """
    global _model_index
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    or_headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/video-to-shorts-automation",
        "X-Title": "video-to-shorts-automation",
    }

    models = settings.openrouter_models
    start = min(_model_index, len(models) - 1)
    or_error: Exception | None = None
    for mi in range(start, len(models)):
        try:
            content = await _chat_once(dict(payload, model=models[mi]), or_headers, API_URL)
            _model_index = mi
            return content
        except LLMError as exc:  # permanent OR retries exhausted (e.g. daily rate limit)
            or_error = exc
            if mi + 1 < len(models):
                log.warning(
                    f"Model '{models[mi]}' failed ({exc}) — "
                    f"falling back to '{models[mi + 1]}'"
                )

    if settings.gemini_api_key:
        log.warning(
            f"All OpenRouter models failed ({or_error}) — "
            f"falling back to Gemini '{settings.gemini_model}'"
        )
        gm_headers = {
            "Authorization": f"Bearer {settings.gemini_api_key}",
            "Content-Type": "application/json",
        }
        # low reasoning effort: clip finding doesn't need deep thinking and
        # thinking tokens count against max_tokens on Gemini 3 models
        gm_payload = dict(payload, model=settings.gemini_model, reasoning_effort="low")
        return await _chat_once(gm_payload, gm_headers, GEMINI_API_URL)
    raise or_error  # type: ignore[misc]


async def _chat_once(payload: dict, headers: dict, api_url: str) -> str:
    """One model, with transient-error retries."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(api_url, headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise LLMError(f"OpenRouter transient error {resp.status_code}: {resp.text[:300]}")
            if resp.status_code >= 400:
                raise PermanentLLMError(
                    f"OpenRouter error {resp.status_code} — check OPENROUTER_API_KEY "
                    f"and OPENROUTER_MODEL: {resp.text[:300]}"
                )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise LLMError("Empty completion from OpenRouter")
            return content
        except PermanentLLMError:
            raise
        except (httpx.HTTPError, LLMError, KeyError, IndexError, ValueError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = 2**attempt
                log.warning(
                    f"LLM call failed (attempt {attempt}/{MAX_RETRIES}): {exc} — retrying in {wait}s"
                )
                await asyncio.sleep(wait)
    raise LLMError(f"OpenRouter call failed after {MAX_RETRIES} attempts: {last_exc}")


def extract_json(text: str):
    """Pull the first JSON object/array out of an LLM reply.

    Qwen sometimes wraps JSON in ```json fences or adds prose — strip both.
    """
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)
    # find first { or [
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise LLMError(f"No JSON found in LLM reply: {text[:200]}")
    start = min(starts)
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    return obj


async def chat_json(system: str, user: str, temperature: float = 0.4, max_tokens: int = 4000):
    """Chat completion that must return JSON; parses (with one retry on bad JSON)."""
    reply = await chat(system, user, temperature=temperature, max_tokens=max_tokens)
    try:
        return extract_json(reply)
    except (LLMError, json.JSONDecodeError):
        log.warning("LLM reply was not valid JSON — retrying once with stricter instruction")
        reply = await chat(
            system,
            user + "\n\nIMPORTANT: reply with ONLY valid JSON. No prose, no markdown fences.",
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return extract_json(reply)
