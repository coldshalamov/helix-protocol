import pytest

pytest.importorskip("nacl")

from helix import cli, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def _create_event(tmp_path):
    event = event_manager.create_event("abcdef", microblock_size=3)
    encoded = event_manager.nested_miner.encode_header(1, len(b"long")) + b"long"
    event_manager.accept_mined_seed(event, 0, encoded)
    event_manager.save_event(event, str(tmp_path / "events"))
    return event


def test_remine_requires_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    chain = event_manager.nested_miner.encode_header(1, 1) + b"a"
    monkeypatch.setattr("helix.cli.nested_miner.find_nested_seed", lambda block, **kw: (chain, 1))
    monkeypatch.setattr("helix.cli.nested_miner.verify_nested_seed", lambda c, b: True)

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
    _, l = event_manager.nested_miner.decode_header(hdr)
    assert reloaded["seeds"][0][1 : 1 + l] == b"long"


def test_remine_with_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    chain = event_manager.nested_miner.encode_header(1, 1) + b"a"
    monkeypatch.setattr("helix.cli.nested_miner.find_nested_seed", lambda block, **kw: (chain, 1))
    monkeypatch.setattr("helix.cli.nested_miner.verify_nested_seed", lambda c, b: True)

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
    hdr = reloaded["seeds"][0][0]
    _, l = event_manager.nested_miner.decode_header(hdr)
    assert reloaded["seeds"][0][1 : 1 + l] == b"a"
