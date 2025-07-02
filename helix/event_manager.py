import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import os
import tempfile

from datetime import datetime
from nacl import signing

from .config import GENESIS_HASH
from .signature_utils import verify_signature, sign_data, generate_keypair
import time
from .merkle_utils import build_merkle_tree as _build_merkle_tree
from . import nested_miner, betting_interface
from .betting_interface import get_bets_for_event
from .ledger import apply_mining_results
from .statement_registry import finalize_statement
from .minihelix import G, DEFAULT_MICROBLOCK_SIZE
import blockchain

FINAL_BLOCK_PADDING_BYTE = b"\x00"

# Maximum total microblock bytes to keep in memory before spilling to disk
MAX_RAM_MICROBLOCK_BYTES = 10 * 1024 * 1024  # 10MB

# Map of event_id -> temporary directory containing spilled microblocks
_MICROBLOCK_STORES: Dict[str, str] = {}

LAST_FINALIZED_HASH = GENESIS_HASH
LAST_FINALIZED_TIME = 0.0


def sha256(data: bytes) -> str:
    """Return hex encoded SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()

# ... all other functions from your provided code continue unmodified ...
