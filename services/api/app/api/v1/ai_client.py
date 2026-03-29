"""
AIClient — thin wrapper around the Ollama HTTP API.

Configurable at runtime via system_config (no restart required).
All calls are best-effort: any failure returns None and scoring falls back
to rule-only deterministic mode.
"""
from __future__ import annotations

import json

import httpx


class AIClient:
    """
    Wraps Ollama's /api/generate endpoint for two scoring-support tasks:
      1. score_attribution_confidence  — does this event involve this politician?
      2. score_event_significance      — how politically significant is this event?
    """

    DEFAULT_BASE_URL = "http://10.11.235.71:11434"
    DEFAULT_MODEL = "mistral"
    GENERATE_TIMEOUT = 20.0

    def __init__(self, base_url: str, model: str, enabled: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.enabled = enabled

    @classmethod
    def from_config(cls, config: dict) -> "AIClient":
        return cls(
            base_url=str(config.get("ai_base_url", cls.DEFAULT_BASE_URL)),
            model=str(config.get("ai_model", cls.DEFAULT_MODEL)),
            enabled=bool(config.get("ai_enabled", False)),
        )

    # ── internal ────────────────────────────────────────────────────────────

    def _generate(self, prompt: str) -> str | None:
        if not self.enabled:
            return None
        try:
            with httpx.Client(timeout=self.GENERATE_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"ai_client warning: generate failed — {exc}", flush=True)
            return None

    def generate_structured(self, prompt: str) -> dict | None:
        """
        Call Ollama with format="json" to get a schema-constrained JSON response.

        Used by NewsAnalysisClient for story clustering and significance assessment.
        Returns the parsed dict or None on any failure.
        """
        if not self.enabled:
            return None
        try:
            with httpx.Client(timeout=self.GENERATE_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip()
                if not raw:
                    return None
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"ai_client warning: generate_structured failed — {exc}", flush=True)
            return None

    @staticmethod
    def _extract_json(raw: str) -> dict | None:
        """Find and parse the first JSON object in a string."""
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(raw[start:end])
        except Exception:  # noqa: BLE001
            return None

    # ── public API ───────────────────────────────────────────────────────────

    def score_attribution_confidence(
        self,
        event_title: str,
        event_summary: str,
        politician_name: str,
        politician_role: str,
    ) -> float | None:
        """
        Ask Ollama: does this event directly involve this politician?
        Returns a confidence float 0.0–1.0, or None if AI is disabled/unavailable.
        Used by AttributionEngine to augment name-match confidence scores.
        """
        prompt = (
            "You are a Canadian political news classifier.\n"
            f'Event headline: "{event_title}"\n'
            f'Event summary: "{event_summary[:400]}"\n'
            f"Politician: {politician_name} ({politician_role})\n\n"
            "Does this news event directly involve or significantly concern this politician?\n"
            'Respond with a JSON object only, no other text: {"confidence": <float 0.0-1.0>, "reason": "<10 words max>"}'
        )
        raw = self._generate(prompt)
        if raw is None:
            return None
        data = self._extract_json(raw)
        if data is None:
            return None
        try:
            return max(0.0, min(1.0, float(data["confidence"])))
        except (KeyError, TypeError, ValueError):
            return None

    def score_event_significance(
        self,
        event_title: str,
        event_type: str,
        jurisdiction: str,
    ) -> dict | None:
        """
        Ask Ollama: how politically significant is this event?
        Returns {"significance": 1-10, "multiplier": 0.5-2.0, "reason": str} or None.
        The multiplier is applied (weighted by ai_confidence_weight) to the rule score.
        """
        prompt = (
            "You are a Canadian political analyst.\n"
            f'Event: "{event_title}"\n'
            f"Type: {event_type}, Jurisdiction: {jurisdiction}\n\n"
            "Rate this event's political significance and suggest a scoring multiplier.\n"
            "Significance 1=trivial, 10=historic. Multiplier 0.5=minor, 1.0=normal, 2.0=major.\n"
            'Respond with JSON only: {"significance": <1-10>, "multiplier": <0.5-2.0>, "reason": "<15 words max>"}'
        )
        raw = self._generate(prompt)
        if raw is None:
            return None
        data = self._extract_json(raw)
        if data is None:
            return None
        try:
            return {
                "significance": max(1, min(10, int(data.get("significance", 5)))),
                "multiplier": max(0.5, min(2.0, float(data.get("multiplier", 1.0)))),
                "reason": str(data.get("reason", ""))[:200],
            }
        except (TypeError, ValueError):
            return None

    def is_available(self) -> bool:
        """Ping Ollama to check availability. Used in /admin/config health check."""
        if not self.enabled:
            return False
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False
