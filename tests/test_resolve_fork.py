import sys
import types
import blockchain as bc
import helix.blockchain as blockchain

import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    stub = types.ModuleType("helix.nested_miner")
    stub.verify_nested_seed = lambda chain, block: True
    sys.modules["helix.nested_miner"] = stub
    monkeypatch.setattr(em, "nested_miner", stub)


def _make_event(tmp_path, text, chain_file):
    """Create, mine and finalize a single-block event."""
    event = em.create_event(text, microblock_size=len(text))
    enc = bytes([1, 1]) + b"a"
    em.accept_mined_seed(event, 0, enc)
    em.finalize_event(
        event,
        node_id="X",
        chain_file=str(chain_file),
        _bc=blockchain,
    )
    em.save_event(event, str(tmp_path / "events"))
    return event


def test_resolve_fork_adopts_heavier(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    chain_file_local = tmp_path / "local.jsonl"
    chain_file_remote = tmp_path / "remote.jsonl"

    # monkeypatch append_block to use separate chain files
    def _append_block_local(h, chain_file=chain_file_local):
        bc.append_block(h, path=str(chain_file))

    def _append_block_remote(h, chain_file=chain_file_remote):
        bc.append_block(h, path=str(chain_file))

    monkeypatch.setattr(em, "append_block", _append_block_local)
    _make_event(tmp_path, "one", chain_file_local)
    local_chain = bc.load_chain(str(chain_file_local))

    # remote chain has evt1 then evt2 making it longer and heavier
    monkeypatch.setattr(em, "append_block", _append_block_remote)
    _make_event(tmp_path, "one", chain_file_remote)
    _make_event(tmp_path, "two", chain_file_remote)
    remote_chain = bc.load_chain(str(chain_file_remote))

    chosen = bc.resolve_fork(local_chain, remote_chain, events_dir=str(events_dir))
    assert chosen == remote_chain
