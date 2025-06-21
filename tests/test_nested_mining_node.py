import pytest

pytest.importorskip("nacl")

pytestmark = pytest.mark.skip(reason="Legacy miner deprecated")

from helix.helix_node import HelixNode
from helix.gossip import LocalGossipNetwork
from helix import minihelix, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_nested_mining_fallback(tmp_path, monkeypatch):
    network = LocalGossipNetwork()
    node = HelixNode(
        events_dir=str(tmp_path / "events"),
        balances_file=str(tmp_path / "balances.json"),
        network=network,
        microblock_size=2,
        max_nested_depth=3,
    )

    # Disable real mining behavior
    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda target: None)

    # Fake successful nested mining
    chain = [b"a", minihelix.G(b"a", 2)]
    monkeypatch.setattr(
        "helix.helix_node.exhaustive_miner.exhaustive_mine",
        lambda target, **kwargs: chain,
    )

    # Create and register event
    event = node.create_event("ab", private_key=None)
    evt_id = event["header"]["statement_id"]
    node.events[evt_id] = event

    # Mine it using fallback
    node.mine_event(event)

    assert event["is_closed"]
    assert event["seed_depths"][0] == 2
