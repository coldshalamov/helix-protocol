import os
import sys
import pytest

# Ensure project root on path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib

pytest.importorskip("nacl")


def test_module_imports():
    importlib.import_module('helix.event_manager')
    importlib.import_module('helix.helix_node')
    importlib.import_module('helix.minihelix')
    importlib.import_module('helix.betting_interface')
    importlib.import_module('helix.signature_utils')

