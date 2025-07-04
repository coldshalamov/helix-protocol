import pytest

pytest.importorskip("nacl")

pytestmark = pytest.mark.skip(reason="Legacy miner deprecated")

from helix import helix_cli as cli, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def _create_event(tmp_path):
    event = event_manager.create_event("abcdef", microblock_size=3)
    encoded = bytes([1, len(b"long")]) + b"long"
    event_manager.accept_mined_seed(event, 0, encoded)
    event_manager.save_event(event, str(tmp_path / "events"))
    return event


def test_remine_requires_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    chain = [b"a"]
    monkeypatch.setattr(
        "helix.helix_cli.exhaustive_miner.exhaustive_mine",
        lambda block, **kw: chain,
    )
    monkeypatch.setattr(
        "helix.helix_cli.nested_miner.verify_nested_seed",
        lambda c, b: True,
    )

    cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "remine-microblock",
            "--event-id",
            evt_id,
            "--index",
            "0",
        ]
    )
    reloaded = event_manager.load_event(str(tmp_path / "events" / f"{evt_id}.json"))
    hdr = reloaded["seeds"][0][0]
    l = reloaded["seeds"][0][1]
    assert reloaded["seeds"][0][2 : 2 + l] == b"long"


def test_remine_with_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    chain = [b"a"]
    monkeypatch.setattr(
        "helix.helix_cli.exhaustive_miner.exhaustive_mine",
        lambda block, **kw: chain,
    )
    monkeypatch.setattr(
        "helix.helix_cli.nested_miner.verify_nested_seed",
        lambda c, b: True,
    )

    cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "remine-microblock",
            "--event-id",
            evt_id,
            "--index",
            "0",
            "--force",
        ]
    )
    reloaded = event_manager.load_event(str(tmp_path / "events" / f"{evt_id}.json"))
    assert reloaded["seeds"][0] == chain
