from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_id() -> str:
    now = utcnow()
    return now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
