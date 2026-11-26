"""App settings, read from environment variables or a .env file.

Nothing secret lives in the code. Copy .env.example (at the repo root) to .env and fill it in.
Docker Compose passes the root .env to the container; when you run the backend directly
from the backend/ folder, the root .env is read too (backend/.env also works).
"""
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    # Supabase. If SUPABASE_URL is empty (or still the placeholder from .env.example),
    # the app runs in "dev mode": tasks are kept in memory and every request belongs
    # to a single test user, so you can try everything from /docs without a database.
    supabase_url: str = ""
    # The anon/public key. Never the service_role key: requests act as the student so RLS applies.
    supabase_key: str = Field("", validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_ANON_KEY"))
    tasks_table: str = "tasks"
    courses_table: str = "courses"

    # Gemini. If GEMINI_API_KEY is empty, tasks are saved without AI fields.
    gemini_api_key: str = ""
    # flash-lite answers quickly and is enough for classifying assignments;
    # bigger models (gemini-3.8-flash) kept timing out on the free tier.
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = 60.0
    # How much the model "thinks" before answering: minimal / low / medium / high.
    # Sorting assignments is simple, so "minimal" keeps it fast. Empty = model default.
    gemini_thinking_level: str = "minimal"

    # Which websites may call the API from a browser (the dashboard, the extension).
    # Comma-separated, e.g. "http://localhost:5173,chrome-extension://abcdefg"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Where the link in the verification email sends a new student (the dashboard's address).
    # Empty = use the "Site URL" from the Supabase dashboard. To change it, also add the address under
    # Authentication -> URL Configuration -> Redirect URLs in Supabase.
    frontend_url: str = ""

    # Safety limit on how many tasks one sync request may send.
    max_tasks_per_sync: int = 200

    @property
    def dev_mode(self) -> bool:
        return not self.supabase_url.startswith("http")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
