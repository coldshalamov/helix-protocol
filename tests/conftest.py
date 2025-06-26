import importlib.util
import pytest

if importlib.util.find_spec("nacl") is None:
    raise pytest.UsageError(
        "PyNaCl is required for the test suite. Install dependencies with 'pip install -r requirements.txt'."
    )
