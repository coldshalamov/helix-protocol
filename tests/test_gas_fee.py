import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode
from helix.gossip import LocalGossipNetwork
from helix import signature_utils


def test_gas_fee_deducted(tmp_path):
    network = LocalGossipNetwork()
    node = HelixNode(
        events_dir=str(tmp_path / "events"),
        balances_file=str(tmp_path / "balances.json"),
        network=network,
        microblock_size=2,
    )
    pub, priv = signature_utils.generate_keypair()
    node.balances[pub] = 10

    event = node.create_event("hello", private_key=priv)
    fee = event["header"].get("gas_fee")
    assert fee == event["header"]["block_count"]
    assert node.balances[pub] == 10 - fee
