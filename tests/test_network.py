import pytest

from helix.network import TCPGossipTransport, SocketGossipNetwork, Peer


def test_tcp_transport_loopback():
    transport = TCPGossipTransport(host="127.0.0.1", port=0)
    peer = Peer("127.0.0.1", transport.port)
    transport.add_peer(peer)
    transport.send(peer, {"msg": "hello"})
    recv_peer, msg = transport.receive(timeout=1)
    assert msg == {"msg": "hello"}
    transport.close()

