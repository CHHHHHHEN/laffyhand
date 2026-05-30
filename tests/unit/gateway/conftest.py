from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def runtime():
    return MagicMock()


@pytest.fixture
def transport():
    t = MagicMock()
    t.send = AsyncMock()
    return t
