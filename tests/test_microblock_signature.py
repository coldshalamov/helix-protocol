import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode, GossipMessageType
from helix.gossip import LocalGossipNetwork
from helix import event_manager, signature_utils, minihelix


def test_signed_microblock_replacement(tmp_path):
    network = LocalGossipNetwork()
    pub, priv = signature_utils.generate_keypair()
    node_a = HelixNode(
        events_dir=str(tmp_path / "a_events"),
        balances_file=str(tmp_path / "a_bal.json"),
        node_id="A",
        network=network,
        microblock_size=2,
        public_key=pub,
        private_key=priv,
    )
    node_b = HelixNode(
        events_dir=str(tmp_path / "b_events"),
        balances_file=str(tmp_path / "b_bal.json"),
        node_id="B",
        network=network,
        microblock_size=2,
    )

    event = node_a.create_event("ab")
    evt_id = event["header"]["statement_id"]
    node_a.events[evt_id] = event
    node_b.events[evt_id] = event_manager.create_event("ab", microblock_size=2)

    event_b = node_b.events[evt_id]
    enc = event_manager.nested_miner.encode_header(3, len(b"long")) + b"long"
    event_manager.accept_mined_seed(event_b, 0, enc)

    seed = b"a"
    payload = f"{evt_id}:0:{seed.hex()}".encode("utf-8")
    sig = signature_utils.sign_data(payload, priv)
    msg = {
        "type": GossipMessageType.MINED_MICROBLOCK,
        "event_id": evt_id,
        "index": 0,
        "seed": seed.hex(),
        "pubkey": pub,
        "signature": sig,
    }
    node_b._handle_message(msg)
    block = event_b["microblocks"][0]
    N = len(block)
    expected = [seed]
    current = seed
    while True:
        current = minihelix.G(current, N)
        if current == block:
            break
        expected.append(current)
    assert event_b["seeds"][0] == expected
    assert event_b["seed_depths"][0] == len(expected)

    wrong = msg.copy()
    wrong["signature"] = signature_utils.sign_data(b"bad", priv)
    node_b._handle_message(wrong)
    assert event_b["seeds"][0] == expected

