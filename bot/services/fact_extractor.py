import json
import logging
import re
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.models import MemoryFact, DialogMessage
from bot.config import settings

logger = logging.getLogger(__name__)


FACT_EXTRACTION_PROMPT = """Проанализируй следующий диалог и извлеки ключевые факты о пользователе.

Правила:
- Извлекай ТОЛЬКО конкретные факты о пользователе (имя, возраст, работа, интересы, предпочтения, события жизни)
- НЕ извлекай общие знания или факты об окружающем мире
- НЕ извлекай мнения ассистента
- Каждый факт должен быть кратким (1 предложение)
- Если фактов нет — верни пустой список

Верни ответ СТРОГО в формате JSON-массива строк. Никакого другого текста.

Примеры правильного ответа:
["Пользователя зовут Алексей", "Работает программистом в Яндексе", "Любит играть в шахматы"]
["Учится в МГУ на 3 курсе", "Интересуется машинным обучением"]
[]

Диалог:
{conversation}

JSON-массив фактов:"""


def parse_facts_response(raw: str) -> list[str]:
    """Parse LLM response into a list of fact strings.

    Uses a 4-level fallback chain for maximum reliability.
    """
    raw = raw.strip()

    # Level 1: Direct JSON parse
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(item).strip() for item in result if str(item).strip()]
        logger.warning("JSON parsed but not a list: %s", type(result))
    except json.JSONDecodeError:
        pass

    # Level 2: Regex — find JSON array anywhere in text
    array_match = re.search(r'\[([^\[\]]*)\]', raw, re.DOTALL)
    if array_match:
        try:
            result = json.loads(array_match.group(0))
            if isinstance(result, list):
                return [str(item).strip() for item in result if str(item).strip()]
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
        return facts

    # Level 4: Treat entire response as a single fact (last resort)
    if len(raw) > 10 and not raw.startswith(('[', '{', 'Ошибка', 'Error')):
        logger.warning("Used single-fact fallback for response: %.100s...", raw)
        return [raw]

    logger.warning("Could not parse any facts from response: %.200s...", raw)
    return []


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
    llm: "LLMService",
) -> None:
    """Background task: extract facts from recent messages.

    Creates its own DB session for isolation. Never raises — all
    exceptions are caught and logged.
    """
    from sqlalchemy import select

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
                return

            conversation_text = "\n".join(
                f"{'Пользователь' if m.role == 'user' else 'Ассистент'}: {m.content}"
                for m in messages
            )

            prompt = FACT_EXTRACTION_PROMPT.format(conversation=conversation_text)
            raw_response = await llm.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )

            facts = parse_facts_response(raw_response)

            if facts:
                # Get existing facts for deduplication
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

                new_facts = deduplicate_facts(facts, existing_facts)

                for fact_text in new_facts:
                    fact = MemoryFact(
                        user_id=user_id,
                        avatar_id=avatar_id,
                        fact_text=fact_text.strip(),
                    )
                    session.add(fact)

                await session.commit()
                logger.info(
                    "Extracted %d new facts for user=%d avatar=%d",
                    len(new_facts), user_id, avatar_id,
                )

        except Exception:
            await session.rollback()
            logger.exception(
                "Fact extraction failed for user=%d avatar=%d",
                user_id, avatar_id,
            )
