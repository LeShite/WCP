import socket

import pytest

from wcp.protocol import MAX_MSG, recv_msg, send_msg


def test_roundtrip():
    a, b = socket.socketpair()
    with a, b:
        send_msg(a, {"op": "ping", "n": 1})
        assert recv_msg(b) == {"op": "ping", "n": 1}


def test_closed_socket_returns_none():
    a, b = socket.socketpair()
    a.close()
    with b:
        assert recv_msg(b) is None


def test_oversized_message_raises():
    a, b = socket.socketpair()
    with a, b:
        a.sendall((MAX_MSG + 1).to_bytes(4, "big"))
        with pytest.raises(ValueError):
            recv_msg(b)
