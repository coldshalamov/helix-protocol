import pytest

pytest.importorskip("nacl")

from helix import helix_cli, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_helix_cli_token_stats(tmp_path, capsys):
    event = event_manager.create_event("stats", microblock_size=2)
    for idx, block in enumerate(event["microblocks"]):
        event_manager.accept_mined_seed(event, idx, [b"a"])
    event_manager.save_event(event, str(tmp_path / "events"))
    capsys.readouterr()

    helix_cli.main(["token-stats", "--data-dir", str(tmp_path)])
    out_lines = capsys.readouterr().out.strip().splitlines()
    expected = sum(event["rewards"]) - sum(event["refunds"])
    assert f"Total HLX Supply: {expected:.4f}" in out_lines[0]
    assert "Total Mined Events: 1" in out_lines[1]
    assert f"Average Reward/Event: {expected:.4f}" in out_lines[2]
