import importlib.util
import os
import random
import time
import pytest

if importlib.util.find_spec("nacl") is None:
    raise pytest.UsageError(
        "PyNaCl is required for the test suite. Install dependencies with 'pip install -r requirements.txt'."
    )


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    """Provide deterministic OS, random and time functions for tests."""

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(os, "urandom", lambda n: b"\0" * n)
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
