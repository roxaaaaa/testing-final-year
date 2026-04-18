"""Pytest: force test env before importing the app (isolated from .env)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-used-in-unit-tests")

from server import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c
