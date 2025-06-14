import hashlib
import json
from pathlib import Path
import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode, GENESIS_HASH
from helix import event_manager


def test_genesis_loaded(tmp_path):
    genesis_src = Path('genesis.json')
    data = genesis_src.read_bytes()
    assert hashlib.sha256(data).hexdigest() == GENESIS_HASH

    node = HelixNode(events_dir=str(tmp_path/'events'),
                     balances_file=str(tmp_path/'balances.json'),
                     genesis_file=str(genesis_src))
    assert node.genesis == json.loads(data.decode('utf-8'))

    event = node.create_event('genesis check')
    assert event['header']['parent_id'] == GENESIS_HASH

    node.import_event(event)
    node.save_state()

    node2 = HelixNode(events_dir=str(tmp_path/'events'),
                      balances_file=str(tmp_path/'balances.json'),
                      genesis_file=str(genesis_src))
    assert event['header']['statement_id'] in node2.events


def test_invalid_parent_rejected(tmp_path):
    genesis_src = Path('genesis.json')
    node = HelixNode(events_dir=str(tmp_path/'events'),
                     balances_file=str(tmp_path/'balances.json'),
                     genesis_file=str(genesis_src))
    bad = event_manager.create_event('bad')
    bad['header']['parent_id'] = 'wrong'
    with pytest.raises(ValueError):
        node.import_event(bad)

    # create invalid event file and ensure load_state ignores it
    event_manager.save_event(bad, str(tmp_path/'events'))
    node2 = HelixNode(events_dir=str(tmp_path/'events'),
                      balances_file=str(tmp_path/'balances.json'),
                      genesis_file=str(genesis_src))
    assert bad['header']['statement_id'] not in node2.events

