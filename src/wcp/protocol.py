"""Protocolo de comunicación WCP sobre TCP."""
import json
import socket
import struct

MAGIC = b"WCP2"
DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
CHUNK = 1024 * 1024  # 1 MiB
MAX_MSG = 16 * 1024 * 1024
TIMEOUT = 30


def set_keepalive(sock, idle=10, interval=5):
    """Detecta cables/Wi-Fi caídos en ~20 s en vez de esperar al timeout."""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "SIO_KEEPALIVE_VALS"):  # Windows
        sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle * 1000, interval * 1000))
    elif hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)


def send_msg(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack("!I", len(data)))
    sock.sendall(data)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def recv_msg(sock):
    hdr = recv_exact(sock, 4)
    if hdr is None:
        return None
    (size,) = struct.unpack("!I", hdr)
    if size > MAX_MSG:
        raise ValueError("Mensaje excesivo")
    data = recv_exact(sock, size)
    if data is None:
        return None
    return json.loads(data.decode("utf-8"))
