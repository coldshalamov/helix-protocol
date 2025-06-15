import pytest

pytest.importorskip("nacl")

from helix import cli, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_cli_token_stats(tmp_path, capsys):
    event = event_manager.create_event("abcd", microblock_size=2)
    for idx, block in enumerate(event["microblocks"]):
        event_manager.accept_mined_seed(event, idx, [b"a"])
    event_manager.save_event(event, str(tmp_path / "events"))
    capsys.readouterr()  # clear mark_mined output

    cli.main(["--data-dir", str(tmp_path), "token-stats"])
    out = capsys.readouterr().out.strip()
    expected = sum(event["rewards"]) - sum(event["refunds"])
    assert f"Total HLX Issued: {expected:.4f}" in out
