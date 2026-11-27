"""Environment configuration for the eRank MCP server.

Account-specific values (shop, member_id, list_id) are NOT hardcoded.
Set them via .env / MCP env, or leave unset and they are discovered from
/api/dashboard/shop-profile and /api/member-shops after login.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COOKIE_FILE = PROJECT_ROOT / "cookies.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    erank_base_url: str = "https://members.erank.com"
    erank_cookie_file: Optional[Path] = DEFAULT_COOKIE_FILE
    erank_cookie_header: Optional[str] = None

    # Optional overrides — prefer discovery via session when unset
    erank_default_shop: Optional[str] = None
    erank_default_shop_id: Optional[int] = None
    erank_default_member_id: Optional[int] = None
    erank_keyword_list_id: Optional[int] = None

    # Product defaults (not account-specific)
    erank_default_country: str = "GLO"
    erank_default_marketplace: str = "etsy"

    erank_allow_writes: bool = False
    erank_allow_telemetry: bool = False
    erank_warm_session: bool = True

    catalog_path: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "catalog" / "api-catalog.json"
    )

    @field_validator("erank_cookie_file", mode="before")
    @classmethod
    def _empty_cookie_path(cls, v: object) -> object:
        if v is None or v == "":
            return DEFAULT_COOKIE_FILE
        return v


def get_settings() -> Settings:
    return Settings()
