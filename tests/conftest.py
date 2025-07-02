import importlib.util
import time

import pytest

from helix import event_manager, minihelix, signature_utils

if importlib.util.find_spec("nacl") is None:
    raise pytest.UsageError(
        "PyNaCl is required for the test suite. Install dependencies with 'pip install -r requirements.txt'."
    )


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
