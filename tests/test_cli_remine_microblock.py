import pytest

pytest.importorskip("nacl")

from helix import cli, event_manager


def _create_event(tmp_path):
    event = event_manager.create_event("abcdef", microblock_size=3)
    event_manager.accept_mined_seed(event, 0, b"long", 1)
    event_manager.save_event(event, str(tmp_path / "events"))
    return event


def test_remine_requires_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    monkeypatch.setattr(
        "helix.cli.nested_miner.find_nested_seed", lambda block: ([b"a"], 1)
    )
    monkeypatch.setattr(
        "helix.cli.nested_miner.verify_nested_seed", lambda chain, block: True
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
    assert reloaded["seeds"][0] == b"long"


def test_remine_with_force(tmp_path, monkeypatch):
    event = _create_event(tmp_path)
    evt_id = event["header"]["statement_id"]

    monkeypatch.setattr(
        "helix.cli.nested_miner.find_nested_seed", lambda block: ([b"a"], 1)
    )
    monkeypatch.setattr(
        "helix.cli.nested_miner.verify_nested_seed", lambda chain, block: True
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
    assert reloaded["seeds"][0] == b"a"
