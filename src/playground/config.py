"""Environment-driven settings for the playground server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

AuthMode = Literal["mixed", "required", "off"]


@dataclass(frozen=True)
class Settings:
    base_url: str
    port: int
    auth_mode: AuthMode
    google_oauth_client_id: str
    google_oauth_client_secret: str

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode != "off"


def load_settings() -> Settings:
    auth_mode = os.environ.get("AUTH_MODE", "mixed").lower()
    if auth_mode not in ("mixed", "required", "off"):
        raise ValueError(f"AUTH_MODE must be mixed|required|off, got {auth_mode!r}")

    settings = Settings(
        base_url=os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/"),
        port=int(os.environ.get("PORT", "8080")),
        auth_mode=auth_mode,
        google_oauth_client_id=os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        google_oauth_client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    )
    if settings.auth_enabled and not (
        settings.google_oauth_client_id and settings.google_oauth_client_secret
    ):
        raise ValueError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required "
            f"when AUTH_MODE={settings.auth_mode}. Set them in .env or use AUTH_MODE=off."
        )
    return settings
