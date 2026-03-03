from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Telegram
    bot_token: str

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/avatar_bot"

    # OpenRouter / LLM
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-3-flash-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 400
    llm_timeout: float = 60.0
    llm_max_retries: int = 3

    # Memory tuning
    short_term_message_limit: int = 10
    fact_extraction_interval: int = 3
    similarity_threshold: float = 0.75

    # Streaming tuning
    stream_edit_interval: float = 0.8
    stream_min_chunk_length: int = 20


settings = Settings()
