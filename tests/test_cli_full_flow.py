import json
import pytest
import blockchain as bc

pytest.importorskip("nacl")

from helix import helix_cli, event_manager, helix_node, signature_utils


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(helix_cli, "DATA_EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(helix_cli, "EVENTS_DIR", tmp_path / "events")

    def fake_mine(event, max_depth=4):
        for idx in range(event["header"]["block_count"]):
            enc = bytes([1, 1]) + b"a"
            event_manager.accept_mined_seed(event, idx, enc)
        return event["header"]["block_count"], 0.0

    monkeypatch.setattr(helix_node, "mine_microblocks", fake_mine)

    statement = "CLI full flow"
    helix_cli.main(["submit-statement", statement, "--block-size", "4"])
    out_lines = capsys.readouterr().out.strip().splitlines()
    evt_id = out_lines[0].split()[-1]

    helix_cli.main(["mine", evt_id, "--data-dir", str(tmp_path)])
    capsys.readouterr()

    pub1, priv1 = signature_utils.generate_keypair()
    wallet1 = tmp_path / "w1.txt"
    signature_utils.save_keys(str(wallet1), pub1, priv1)
    pub2, priv2 = signature_utils.generate_keypair()
    wallet2 = tmp_path / "w2.txt"
    signature_utils.save_keys(str(wallet2), pub2, priv2)

    helix_cli.main([
        "place-bet",
        "--wallet",
        str(wallet1),
        "--event-id",
        evt_id,
        "--choice",
        "YES",
        "--amount",
        "10",
    ])
    helix_cli.main([
        "place-bet",
        "--wallet",
        str(wallet2),
        "--event-id",
        evt_id,
        "--choice",
        "NO",
        "--amount",
        "5",
    ])
    capsys.readouterr()

    helix_cli.main(["finalize", evt_id])
    capsys.readouterr()

    event_path = tmp_path / "events" / f"{evt_id}.json"
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    assert event["is_closed"]
    payouts = event.get("payouts", {})
    assert pub1 in payouts and payouts[pub1] > 0

    chain = bc.load_chain(str(tmp_path / "blockchain.jsonl"))
    assert chain and chain[-1]["event_ids"][0] == evt_id
