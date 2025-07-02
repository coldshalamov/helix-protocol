import importlib.util
import os
import random
import time
import pytest

from helix import event_manager, minihelix, signature_utils

if importlib.util.find_spec("nacl") is None:
    raise pytest.UsageError(
        "PyNaCl is required for the test suite. Install dependencies with 'pip install -r requirements.txt'."
    )


def pytest_collection_modifyitems(config, items):
    """Automatically add a timeout to mining/compression related tests."""
    keywords = {"mine", "compression", "nested", "integration"}
    for item in items:
        path = str(item.fspath)
        name = item.name
        if any(k in path for k in keywords) or any(k in name for k in keywords):
            item.add_marker(pytest.mark.timeout(2))


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    """Provide deterministic OS, random and time functions for tests."""
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(os, "urandom", lambda n: b"\0" * n)
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)


@pytest.fixture
def dummy_wallet() -> dict:
    """Return a dictionary with a generated Ed25519 keypair."""
    pub, priv = signature_utils.generate_keypair()
    return {"public": pub, "private": priv}


@pytest.fixture
def sample_statement() -> str:
    """Simple statement used across tests."""
    return "Helix test statement"


@pytest.fixture
def sample_event(sample_statement: str) -> dict:
    """Create a new event from :func:`helix.event_manager.create_event`."""
    return event_manager.create_event(sample_statement, microblock_size=2)


@pytest.fixture
def valid_microblock() -> dict:
    """Return a microblock payload and the seed that generates it."""
    seed = b"a"
    block = minihelix.G(seed, 4)
    return {"seed": seed, "block": block}


@pytest.fixture
def patched_time(monkeypatch):
    """Patch ``time.time`` to return deterministic increments."""
    current = [1000.0]

    def fake_time() -> float:
        t = current[0]
        current[0] += 1.0
        return t

    monkeypatch.setattr(time, "time", fake_time)
    return fake_time
