"""Protocolo de comunicación WCP sobre TCP."""
import json
import struct

MAGIC = b"WCP1"
DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
CHUNK = 1024 * 1024  # 1 MiB
MAX_MSG = 16 * 1024 * 1024


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
