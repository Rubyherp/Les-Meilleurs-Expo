"""LLM provider abstraction for coaching report generation."""

from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings

__all__ = ["LLMProvider", "NullProvider", "OpenAIProvider", "create_provider"]


class LLMProvider(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def model_name(self) -> str: ...

    async def chat(self, messages: list[dict], **kwargs) -> str | None: ...


class NullProvider:
    """Fallback provider used when no LLM is configured."""

    available = False
    model_name = "none"

    async def chat(self, messages: list[dict], **kwargs) -> str | None:
        return None


class OpenAIProvider:
    """Lightweight wrapper around OpenAI's async chat API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._client: object | None = None

    @property
    def available(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[dict], **kwargs) -> str | None:
        try:
            from openai import AsyncOpenAI

            client = self._client
            if client is None:
                client = AsyncOpenAI(api_key=self._api_key)
                self._client = client

            response = await client.chat.completions.create(
                model=kwargs.get("model", self._model),
                messages=messages,
                temperature=kwargs.get("temperature", self._temperature),
            )
            return response.choices[0].message.content
        except Exception:
            return None


def create_provider(settings=None) -> LLMProvider:
    """Create an LLM provider based on application settings.

    Returns ``NullProvider`` when no API key is configured or when the
    OpenAI SDK is not available. Never raises.
    """
    s = settings or get_settings()
    if not s.llm_api_key:
        return NullProvider()
    try:
        return OpenAIProvider(
            api_key=s.llm_api_key,
            model=s.llm_model,
            temperature=s.llm_temperature,
        )
    except Exception:
        return NullProvider()
