import gzip
import json
import os

import pytest

pytest.importorskip("nacl")

from helix import event_manager as em
from helix import archive


def _finalize_event(event: dict) -> None:
    for idx in range(event["header"]["block_count"]):
        em.mark_mined(event, idx)


def test_archive_bundles(tmp_path):
    events_dir = tmp_path / "events"
    archives_dir = tmp_path / "archives"

    events = []
    for text in ["a", "b", "c"]:
        ev = em.create_event(text, microblock_size=2)
        _finalize_event(ev)
        em.save_event(ev, str(events_dir))
        events.append(ev)

    paths = archive.archive_finalized_events(str(events_dir), str(archives_dir), bundle_size=2)
    assert len(paths) == 2
    for p, expected_len in zip(paths, [2, 1]):
        assert os.path.exists(p)
        with gzip.open(p, "rb") as fh:
            data = json.load(fh)
        assert data["metadata"]["total_events"] == expected_len
        assert len(data["events"]) == expected_len
        assert data["metadata"]["compression_ratio"] > 0
