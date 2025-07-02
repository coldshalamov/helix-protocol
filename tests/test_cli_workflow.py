import os
import subprocess
import sys
from pathlib import Path

pytest = __import__('pytest')
pytest.importorskip("nacl")


def _run_cli(tmp_path: Path, args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    env = (env or os.environ.copy()).copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    cmd = [sys.executable, "-m", "helix.helix_cli", *args]
    return subprocess.run(cmd, cwd=tmp_path, text=True, capture_output=True, env=env)


def test_help(tmp_path: Path):
    result = _run_cli(tmp_path, ["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_doctor(tmp_path: Path):
    (tmp_path / "data" / "events").mkdir(parents=True)
    (tmp_path / "data" / "balances.json").write_text("{}")
    (tmp_path / "data" / "blockchain.jsonl").write_text("")
    (tmp_path / "wallet.json").write_text("{}")
    (tmp_path / "requirements.txt").write_text("")

    result = _run_cli(tmp_path, ["doctor"])
    assert result.returncode == 0
    assert "System check passed." in result.stdout


def test_mine_mock(tmp_path: Path):
    events = tmp_path / "data" / "events"
    events.mkdir(parents=True)
    (events / "test_evt.json").write_text("{}")

    patch_dir = tmp_path / "patch"
    patch_dir.mkdir()
    (patch_dir / "patchmod.py").write_text(
        """event={'header':{'statement_id':'test_evt','block_count':1},'microblocks':[b'aa'],'seeds':[None]}

def setup():
    import helix.event_manager as em, helix.minihelix, helix.nested_miner
    em.load_event=lambda p:event
    em.save_event=lambda ev,d:None
    em.mark_mined=lambda ev,i:None
    helix.minihelix.mine_seed=lambda block:b'aa'
    helix.nested_miner.verify_nested_seed=lambda c,b:True
"""
    )
    (patch_dir / "sitecustomize.py").write_text("import patchmod; patchmod.setup()\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{patch_dir}{os.pathsep}{os.getcwd()}"
    result = _run_cli(tmp_path, ["mine", "test_evt"], env=env)

    assert result.returncode == 0
    assert result.stdout.strip() == ""
