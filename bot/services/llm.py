import asyncio
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI, RateLimitError, APIConnectionError, APIError

logger = logging.getLogger(__name__)


class LLMService:
    """OpenRouter LLM provider using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "google/gemini-3-flash-preview",
        timeout: float = 60.0,
        max_retries: int = 3,
        default_max_tokens: int = 400,
        default_temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = 1.0
        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,  # we handle retries ourselves
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Full (non-streaming) chat completion with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens or self.default_max_tokens,
                    temperature=temperature if temperature is not None else self.default_temperature,
                    stream=False,
                )
                return response.choices[0].message.content or ""

            except RateLimitError:
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(
                    "Rate limited, retrying in %.1fs (attempt %d/%d)",
                    delay, attempt + 1, self.max_retries,
                )
                await asyncio.sleep(delay)

            except APIConnectionError:
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(
                    "Connection error, retrying in %.1fs (attempt %d/%d)",
                    delay, attempt + 1, self.max_retries,
                )
                await asyncio.sleep(delay)

            except APIError as e:
                logger.error("API error (attempt %d/%d): %s", attempt + 1, self.max_retries, e)
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        raise RuntimeError("Max retries exceeded for LLM chat call")

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Streaming chat completion. Yields text chunks with retry logic."""
        for attempt in range(self.max_retries):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens or self.default_max_tokens,
                    temperature=temperature if temperature is not None else self.default_temperature,
                    stream=True,
                )

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
                return  # success — exit retry loop

            except (RateLimitError, APIConnectionError) as e:
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(
                    "Stream error (%s), retrying in %.1fs (attempt %d/%d)",
                    type(e).__name__, delay, attempt + 1, self.max_retries,
                )
                await asyncio.sleep(delay)

            except APIError as e:
                logger.error(
                    "Stream API error (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, e,
                )
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        raise RuntimeError("Max retries exceeded for streaming LLM call")
