from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.models import MemoryFact, DialogMessage
from bot.config import settings

if TYPE_CHECKING:
    from bot.services.llm import LLMService

logger = logging.getLogger(__name__)


FACT_EXTRACTION_PROMPT = """Проанализируй следующий диалог и извлеки ключевые факты о пользователе.

Правила:
- Извлекай ТОЛЬКО конкретные факты о пользователе (имя, возраст, работа, интересы, предпочтения, события жизни)
- НЕ извлекай общие знания или факты об окружающем мире
- НЕ извлекай мнения ассистента
- Каждый факт должен быть кратким (1 предложение)
- Если фактов нет — верни пустой список

{existing_facts_section}

Верни ответ СТРОГО в формате JSON-объекта с двумя полями:
- "add" — массив новых фактов для запоминания
- "outdated" — массив устаревших фактов из списка выше, которые ПРОТИВОРЕЧАТ новой информации из диалога (например, пользователь сменил работу, переехал, изменил интересы). Если противоречий нет — пустой массив.

Примеры правильного ответа:
{{"add": ["Пользователя зовут Алексей", "Работает программистом в Яндексе"], "outdated": []}}
{{"add": ["Теперь работает в Google"], "outdated": ["Работает программистом в Яндексе"]}}
{{"add": [], "outdated": []}}

Диалог:
{conversation}

JSON-объект:"""


def _extract_list(items: object) -> list[str]:
    """Convert parsed JSON items to a clean list of strings."""
    if isinstance(items, list):
        return [str(item).strip() for item in items if str(item).strip()]
    return []


def parse_facts_response(raw: str) -> dict[str, list[str]]:
    """Parse LLM response into add/outdated fact lists.

    Supports both new dict format {"add": [...], "outdated": [...]}
    and legacy list format [...] with 4-level fallback chain.
    """
    raw = raw.strip()

    # Level 1: Direct JSON parse
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return {
                "add": _extract_list(result.get("add", [])),
                "outdated": _extract_list(result.get("outdated", [])),
            }
        if isinstance(result, list):
            return {"add": _extract_list(result), "outdated": []}
    except json.JSONDecodeError:
        pass

    # Level 2: Regex — find JSON object or array anywhere in text
    obj_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if obj_match:
        try:
            result = json.loads(obj_match.group(0))
            if isinstance(result, dict):
                return {
                    "add": _extract_list(result.get("add", [])),
                    "outdated": _extract_list(result.get("outdated", [])),
                }
        except json.JSONDecodeError:
            pass

    array_match = re.search(r'\[([^\[\]]*)\]', raw, re.DOTALL)
    if array_match:
        try:
            result = json.loads(array_match.group(0))
            if isinstance(result, list):
                return {"add": _extract_list(result), "outdated": []}
        except json.JSONDecodeError:
            pass

    # Level 3: Line-based parsing — strip bullets/numbers
    lines = raw.split('\n')
    facts = []
    for line in lines:
        line = line.strip()
        line = re.sub(r'^[\d]+[.)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = line.strip('"\'')
        line = line.strip()
        if line and len(line) > 5:
            facts.append(line)

    if facts:
        logger.info("Used line-based fallback parsing, got %d facts", len(facts))
        return {"add": facts, "outdated": []}

    # Level 4: Treat entire response as a single fact (last resort)
    if len(raw) > 10 and not raw.startswith(('[', '{', 'Ошибка', 'Error')):
        logger.warning("Used single-fact fallback for response: %.100s...", raw)
        return {"add": [raw], "outdated": []}

    logger.warning("Could not parse any facts from response: %.200s...", raw)
    return {"add": [], "outdated": []}


def deduplicate_facts(
    new_facts: list[str],
    existing_facts: list[str],
) -> list[str]:
    """Remove semantically duplicate facts using string similarity.

    Uses difflib.SequenceMatcher with configurable threshold.
    Works well for Russian text since it operates on character sequences.
    """
    threshold = settings.similarity_threshold
    unique_facts = []

    for new_fact in new_facts:
        new_lower = new_fact.lower().strip()
        is_duplicate = False

        for existing in existing_facts:
            existing_lower = existing.lower().strip()
            ratio = SequenceMatcher(None, new_lower, existing_lower).ratio()
            if ratio > threshold:
                is_duplicate = True
                logger.debug(
                    "Duplicate detected (%.2f): '%s' ~ '%s'",
                    ratio, new_fact, existing,
                )
                break

        if not is_duplicate:
            # Also check against other new facts already in this batch
            for already_added in unique_facts:
                ratio = SequenceMatcher(
                    None, new_lower, already_added.lower()
                ).ratio()
                if ratio > threshold:
                    is_duplicate = True
                    break

        if not is_duplicate:
            unique_facts.append(new_fact)

    return unique_facts


async def extract_facts_background(
    user_id: int,
    avatar_id: int,
    session_factory: async_sessionmaker,
    llm: LLMService,
) -> list[str]:
    """Background task: extract facts from recent messages.

    Creates its own DB session for isolation. Never raises — all
    exceptions are caught and logged.
    Returns list of newly added fact texts (for notification).
    """
    from sqlalchemy import select

    from bot.database.repositories.fact import FactRepository

    async with session_factory() as session:
        try:
            # Get recent messages
            stmt = (
                select(DialogMessage)
                .where(
                    DialogMessage.user_id == user_id,
                    DialogMessage.avatar_id == avatar_id,
                )
                .order_by(DialogMessage.created_at.desc())
                .limit(settings.short_term_message_limit)
            )
            result = await session.execute(stmt)
            messages = list(reversed(result.scalars().all()))

            if not messages:
                return []

            conversation_text = "\n".join(
                f"{'Пользователь' if m.role == 'user' else 'Ассистент'}: {m.content}"
                for m in messages
            )

            # Get existing facts for contradiction detection
            existing_stmt = (
                select(MemoryFact.fact_text)
                .where(
                    MemoryFact.user_id == user_id,
                    MemoryFact.avatar_id == avatar_id,
                    MemoryFact.is_active.is_(True),
                )
            )
            existing_result = await session.execute(existing_stmt)
            existing_facts = [row[0] for row in existing_result.all()]

            # Build extraction prompt with existing facts context
            if existing_facts:
                facts_section = (
                    "Текущие известные факты о пользователе:\n"
                    + "\n".join(f"- {f}" for f in existing_facts)
                    + "\n\nЕсли в диалоге есть информация, ПРОТИВОРЕЧАЩАЯ "
                    "этим фактам, добавь устаревший факт в поле \"outdated\"."
                )
            else:
                facts_section = (
                    "Пока нет известных фактов о пользователе."
                )

            prompt = FACT_EXTRACTION_PROMPT.format(
                conversation=conversation_text,
                existing_facts_section=facts_section,
            )
            raw_response = await llm.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )

            parsed = parse_facts_response(raw_response)
            add_facts = parsed.get("add", [])
            outdated_facts = parsed.get("outdated", [])

            # Deactivate outdated facts
            if outdated_facts:
                fact_repo = FactRepository(session)
                deactivated = await fact_repo.deactivate_similar(
                    user_id=user_id,
                    avatar_id=avatar_id,
                    texts=outdated_facts,
                    threshold=settings.similarity_threshold,
                )
                if deactivated:
                    logger.info(
                        "Deactivated %d outdated facts for user=%d avatar=%d",
                        deactivated, user_id, avatar_id,
                    )

            # Add new facts with deduplication
            new_facts: list[str] = []
            if add_facts:
                new_facts = deduplicate_facts(add_facts, existing_facts)

                for fact_text in new_facts:
                    fact = MemoryFact(
                        user_id=user_id,
                        avatar_id=avatar_id,
                        fact_text=fact_text.strip(),
                    )
                    session.add(fact)

            await session.commit()
            if new_facts:
                logger.info(
                    "Extracted %d new facts for user=%d avatar=%d",
                    len(new_facts), user_id, avatar_id,
                )
            return new_facts

        except Exception:
            await session.rollback()
            logger.exception(
                "Fact extraction failed for user=%d avatar=%d",
                user_id, avatar_id,
            )
            return []
