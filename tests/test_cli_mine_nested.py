import pytest

pytest.importorskip("nacl")

pytestmark = pytest.mark.skip(reason="Legacy miner deprecated")

from helix import cli, event_manager, minihelix


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_cli_mine_nested(tmp_path, monkeypatch):
    event = event_manager.create_event("ab", microblock_size=2)
    event_manager.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    seed = b"a"
    subseed = minihelix.G(seed, 2)
    chain = bytes([2, len(seed)]) + seed + subseed

    monkeypatch.setattr(
        "helix.cli.nested_miner.find_nested_seed",
        lambda block, **kwargs: (chain, 2),
    )
    monkeypatch.setattr("helix.cli.nested_miner.verify_nested_seed", lambda c, b: True)

    cli.main(["--data-dir", str(tmp_path), "mine", evt_id])

    reloaded = event_manager.load_event(str(tmp_path / "events" / f"{evt_id}.json"))
    assert reloaded["is_closed"]
    assert reloaded["seed_depths"][0] == 2
    hdr = reloaded["seeds"][0][0]
    l = reloaded["seeds"][0][1]
    assert reloaded["seeds"][0][2 : 2 + l] == b"a"
