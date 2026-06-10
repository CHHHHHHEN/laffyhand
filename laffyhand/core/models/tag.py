from __future__ import annotations

from pydantic import BaseModel


class FileTag(BaseModel):
    path: str
    content: str
    updated_at: str
