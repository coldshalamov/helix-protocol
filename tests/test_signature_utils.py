import pytest

pytest.importorskip("nacl")

from helix import signature_utils as su


def test_key_generation_and_sign_verify():
    pub, priv = su.generate_keypair()
    message = b"test message"
    signature = su.sign_data(message, priv)
    assert su.verify_signature(message, signature, pub)


def test_save_and_load_keys(tmp_path):
    pub, priv = su.generate_keypair()
    keyfile = tmp_path / "keys.txt"
    su.save_keys(str(keyfile), pub, priv)
    loaded_pub, loaded_priv = su.load_keys(str(keyfile))
    assert (loaded_pub, loaded_priv) == (pub, priv)


def test_load_or_create_keys(tmp_path):
    keyfile = tmp_path / "wallet.txt"
    pub1, priv1 = su.load_or_create_keys(str(keyfile))
    assert keyfile.exists()
    pub2, priv2 = su.load_or_create_keys(str(keyfile))
    assert (pub1, priv1) == (pub2, priv2)
