"""Shared pytest fixtures for the API service tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.api.v1.ai_client import AIClient


@pytest.fixture()
def mock_session():
    """Return a MagicMock that satisfies SQLAlchemy Session usage."""
    return MagicMock()


@pytest.fixture()
def disabled_ai():
    """Return an AIClient whose enabled flag is False."""
    ai = MagicMock(spec=AIClient)
    ai.enabled = False
    return ai


@pytest.fixture()
def enabled_ai():
    """Return an AIClient whose enabled flag is True."""
    ai = MagicMock(spec=AIClient)
    ai.enabled = True
    return ai
