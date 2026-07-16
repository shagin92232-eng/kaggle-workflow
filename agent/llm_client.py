"""OpenRouter client for Qwen3 — retries, rate-limit backoff, JSON mode."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 4


class LLMError(RuntimeError):
    pass


async def chat(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """Single-turn chat completion. Returns assistant text."""
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/video-to-shorts-automation",
        "X-Title": "video-to-shorts-automation",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(API_URL, headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise LLMError(f"OpenRouter transient error {resp.status_code}: {resp.text[:300]}")
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise LLMError("Empty completion from OpenRouter")
            return content
        except (httpx.HTTPError, LLMError, KeyError) as exc:
            last_exc = exc
            wait = 2**attempt
            log.warning(f"LLM call failed (attempt {attempt}/{MAX_RETRIES}): {exc} — retrying in {wait}s")
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
