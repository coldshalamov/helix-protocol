import pytest

pytest.importorskip("nacl")
pytest.skip("legacy microblock logic removed", allow_module_level=True)

from helix import helix_cli as cli, event_manager as em


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(em, "verify_seed_chain", lambda c, b: True)
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_cli_verify_statement(tmp_path, capsys):
    statement = "verify me"
    event = em.create_event(statement, microblock_size=2)
    enc = bytes([1, 1]) + b"a"
    for idx, _ in enumerate(event["microblocks"]):
        em.accept_mined_seed(event, idx, enc)  # dummy encoded seed
    em.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    path = tmp_path / "events" / f"{evt_id}.json"
    cli.main(["verify-statement", str(path)])
    out = capsys.readouterr().out.strip()
    assert "Verification succeeded" in out
