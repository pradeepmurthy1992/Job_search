"""
Stage-2 semantic scoring client — pluggable backend.

Two options are implemented, both because the candidate asked "what else can
this run on if I can't get a paid Gemini key":

1. GeminiClient — Google's Gemini API DOES have a genuinely free tier via
   Google AI Studio (ai.google.dev): no credit card required, and as of
   Sep 2026 gemini-2.5-flash / gemini-2.0-flash allow roughly 15 requests/
   minute and 1,500 requests/day with a 1M token-per-minute ceiling — far
   more than a 150-250-job-per-run cap will ever hit. The catch: Google's
   terms allow using free-tier inputs for model training, which sits
   awkwardly next to this platform's own "no third-party data sharing"
   non-goal. Fine for a job-search side project; worth knowing before
   sending a full resume through it repeatedly.

2. OllamaClient — a fully local model via Ollama (https://ollama.com),
   completely free, no rate limits, no data ever leaving the machine at all.
   This is actually the better fit for THIS platform's stated design
   philosophy, not just a fallback. Needs a laptop that can run a small
   model reasonably (Qwen3.5 9B or Llama 3.1 8B on 16GB RAM is comfortable;
   drop to Gemma 4B on 8GB machines). Slower and somewhat less sharp at
   nuanced fit-reasoning than Gemini 2.5 Flash, but genuinely free forever.

Pick one in config (see JurisdictionProfile or a global setting) — both
implement the same `score_fit` interface so main.py doesn't care which is
active.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

PROMPT_TEMPLATE = """You are assessing job fit for a candidate. Read the resume summary and the \
job description, then respond with ONLY a JSON object (no markdown fences) shaped exactly like:
{{"score": <0-100 integer>, "reasoning": "<2-3 sentence rationale>"}}

RESUME SUMMARY:
{resume_text}

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description}
"""


@dataclass
class LLMResult:
    score: float
    reasoning: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient(ABC):
    @abstractmethod
    def score_fit(self, resume_text: str, job_title: str, job_description: str) -> LLMResult:
        ...


def _parse_json_response(text: str) -> tuple[float, str]:
    """LLMs sometimes wrap JSON in prose or code fences despite instructions —
    extract the first {...} block rather than trusting a strict json.loads."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return 0.0, f"Could not parse model response: {text[:200]}"
    try:
        parsed = json.loads(match.group(0))
        return float(parsed.get("score", 0)), str(parsed.get("reasoning", ""))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0.0, f"Could not parse model response: {text[:200]}"


class GeminiClient(LLMClient):
    """Free-tier Google AI Studio Gemini API, called directly via REST so no
    extra SDK dependency is required. Get a key at https://aistudio.google.com/apikey
    — no credit card needed for the free tier as of Sep 2026."""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model

    def score_fit(self, resume_text: str, job_title: str, job_description: str) -> LLMResult:
        prompt = PROMPT_TEMPLATE.format(
            resume_text=resume_text, job_title=job_title, job_description=job_description
        )
        url = self.API_URL.format(model=self.model)
        resp = requests.post(
            url,
            params={"key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        score, reasoning = _parse_json_response(text)

        return LLMResult(
            score=score,
            reasoning=reasoning,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
        )


class OllamaClient(LLMClient):
    """Fully local, fully free — talks to a locally-running Ollama daemon.
    Install: https://ollama.com/download, then e.g. `ollama pull qwen2.5:7b`
    (or a model your hardware comfortably fits). No API key, no rate limit,
    no data leaves the machine."""

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def score_fit(self, resume_text: str, job_title: str, job_description: str) -> LLMResult:
        prompt = PROMPT_TEMPLATE.format(
            resume_text=resume_text, job_title=job_title, job_description=job_description
        )
        resp = requests.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=120,  # local inference on modest hardware can be slow
        )
        resp.raise_for_status()
        data = resp.json()

        score, reasoning = _parse_json_response(data.get("response", ""))
        return LLMResult(
            score=score,
            reasoning=reasoning,
            # Ollama reports token counts in eval_count / prompt_eval_count;
            # kept at 0 cost-tracking-wise since local inference has no
            # dollar cost regardless — the platform's token ceiling is a
            # cloud-spend guard, not meaningful for a local model.
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )


def build_client_from_env() -> LLMClient:
    """Convenience factory: reads JOB_INTEL_LLM_BACKEND env var
    ("gemini" | "ollama", default "ollama" since it needs zero setup cost),
    plus GEMINI_API_KEY / OLLAMA_MODEL as needed. Swap this out for direct
    construction if you'd rather wire the choice through config.py instead
    of the environment.
    """
    import os

    backend = os.environ.get("JOB_INTEL_LLM_BACKEND", "ollama").lower()
    if backend == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "JOB_INTEL_LLM_BACKEND=gemini but GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        return GeminiClient(api_key=api_key)
    return OllamaClient(model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))
