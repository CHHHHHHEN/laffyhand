from __future__ import annotations

from pydantic import BaseModel


class FileTag(BaseModel):
    path: str
    message: str
    tags: dict[str, str]
    updated_at: str
    status: str = "active"
    exports: dict[str, str] = {}
    side_effects: str = ""
    depends_on: list[str] = []
