"""Session domain models — only domain-specific models live here."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from laffyhand.core.db.models import ModelID


class TitleConfig(BaseModel):
    mode: Literal["off", "on_create", "on_compact", "auto"] = Field(
        default="auto", description="标题生成模式"
    )
    model: Optional[ModelID] = Field(default=None, description="覆盖 LLM 模型")
    prompt: str = Field(
        default="Generate a concise title (max 8 words) for this coding conversation. "
        "Return only the title, no explanation or punctuation.",
        description="标题生成提示词",
    )
