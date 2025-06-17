import json
import socket
import threading

import pytest

from helix import helix_cli


def test_view_peers(tmp_path, capsys, monkeypatch):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen()

    def _handler():
        conn, _ = server.accept()
        conn.close()
        server.close()

    threading.Thread(target=_handler, daemon=True).start()

    peers = [
        {"node_id": "A", "host": "127.0.0.1", "port": port, "last_seen": 1.0},
        {"node_id": "B", "host": "127.0.0.1", "port": port + 1, "last_seen": 2.0},
    ]
    peers_file = tmp_path / "peers.json"
    peers_file.write_text(json.dumps(peers))

    monkeypatch.chdir(tmp_path)
    helix_cli.main(["view-peers", "--peers-file", str(peers_file)])
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert "A" in out_lines[0] and "reachable=True" in out_lines[0]
    assert "B" in out_lines[1] and "reachable=False" in out_lines[1]
