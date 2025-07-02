import importlib.util
import pytest

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
