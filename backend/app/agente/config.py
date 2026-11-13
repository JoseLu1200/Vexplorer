from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str | None
    model: str | None
    base_url: str = "https://api.openai.com/v1"

    @classmethod
    def from_env(cls) -> "ProviderSettings":
        return cls(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_MODEL"), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model)

    @property
    def unavailable_reason(self) -> str | None:
        missing = []
        if not self.api_key:
            missing.append("OPENAI_API_KEY")
        if not self.model:
            missing.append("OPENAI_MODEL")
        return None if not missing else "missing_server_configuration:" + ",".join(missing)
