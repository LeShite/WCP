import itertools
import os
import socket
import threading
import time

import pytest

from wcp import client as client_mod, protocol, scanner
from wcp.client import SendClient
from wcp.server import ReceiveServer

_ports = itertools.count(18790, 2)  # un puerto por test; +1 lo usa el proxy


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "Documents").mkdir(parents=True)
    monkeypatch.setattr(scanner, "resolve_folder", lambda name: src / name)
    port = next(_ports)
    logs = []
    srv = ReceiveServer(port, "1", tmp_path / "dest", logs.append, lambda *a: None)
    srv.start()
    time.sleep(0.5)
    yield src, tmp_path / "dest", port
    srv.stop()
    time.sleep(1.2)


def send(port):
    logs = []
    c = SendClient("127.0.0.1", port, "1", ["Documents"], logs.append, lambda *a: None)
    c.run()
    return c, logs


def test_transfer_and_skip(env):
    src, dest, port = env
    (src / "Documents" / "a.txt").write_bytes(b"hola")
    c, _ = send(port)
    assert c.ok and (dest / "Documents" / "a.txt").read_bytes() == b"hola"
    assert not list(dest.rglob("*.wcp-part"))
    c, logs = send(port)
    assert c.ok and "0 copiados, 1 saltados" in logs[-1]


def test_resume_partial_file(env):
    src, dest, port = env
    f = src / "Documents" / "big.bin"
    f.write_bytes(os.urandom(3 * 1024 * 1024))
    st = f.stat()
    # cliente que corta tras 1 MB
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(protocol.MAGIC)
    protocol.send_msg(s, {"type": "hello", "pin": "1"})
    assert protocol.recv_msg(s)["type"] == "hello_ok"
    protocol.send_msg(s, {"type": "plan", "dirs": [], "files": [
        ["Documents", "big.bin", st.st_size, st.st_mtime]]})
    assert protocol.recv_msg(s)["offsets"] == [0]
    protocol.send_msg(s, {"type": "file", "folder": "Documents", "relpath": "big.bin",
                          "size": st.st_size, "mtime": st.st_mtime, "offset": 0})
    s.sendall(f.read_bytes()[: protocol.CHUNK])
    time.sleep(0.3)
    s.close()
    time.sleep(0.5)
    assert not (dest / "Documents" / "big.bin").exists()  # nada a medias con nombre final
    c, logs = send(port)
    assert c.ok and any("Reanudando" in m for m in logs)
    assert (dest / "Documents" / "big.bin").read_bytes() == f.read_bytes()


def test_changed_source_does_not_resume(env):
    src, dest, port = env
    f = src / "Documents" / "x.bin"
    f.write_bytes(b"a" * 1000)
    st = f.stat()
    part = dest / "Documents" / f"x.bin.{st.st_size}.{int(st.st_mtime * 1000) + 5}.wcp-part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"zzz")  # parcial de otra versión del origen
    c, logs = send(port)
    assert c.ok and not any("Reanudando" in m for m in logs)
    assert (dest / "Documents" / "x.bin").read_bytes() == b"a" * 1000
    assert not part.exists()


def test_reconnects_after_cut(env, monkeypatch):
    src, dest, port = env
    f = src / "Documents" / "big.bin"
    f.write_bytes(os.urandom(4 * 1024 * 1024))
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(protocol, "TIMEOUT", 3)  # el corte se nota al expirar la lectura
    # proxy que corta la primera conexión tras ~1.5 MB
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", port + 1))
    lsock.listen(2)

    def pipe(a, b, limit=None):
        n = 0
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
                n += len(d)
                if limit and n > limit:
                    break
        except OSError:
            pass
        for x in (a, b):
            try:
                x.close()
            except OSError:
                pass

    def serve():
        for i in range(2):
            c, _ = lsock.accept()
            u = socket.create_connection(("127.0.0.1", port))
            threading.Thread(target=pipe, args=(u, c), daemon=True).start()
            threading.Thread(target=pipe, args=(c, u, 1_500_000 if i == 0 else None),
                             daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    c, logs = send(port + 1)
    lsock.close()
    assert c.ok, logs
    assert any("Reconectando" in m for m in logs) and any("Reanudando" in m for m in logs)
    assert (dest / "Documents" / "big.bin").read_bytes() == f.read_bytes()


def test_wrong_pin_is_fatal_no_retry(env):
    src, _, port = env
    (src / "Documents" / "a.txt").write_bytes(b"x")
    logs = []
    c = SendClient("127.0.0.1", port, "bad", ["Documents"], logs.append, lambda *a: None)
    c.run()
    assert not c.ok and not any("Reconectando" in m for m in logs)


def test_damaged_destination_is_rebuilt(env):
    src, dest, port = env
    (src / "Documents" / "a.txt").write_bytes(b"contenido completo")
    (src / "Documents" / "b.txt").write_bytes(b"otro")
    assert send(port)[0].ok
    (dest / "Documents" / "a.txt").write_bytes(b"conten")  # paquete dañado/truncado
    c, logs = send(port)
    assert c.ok and "1 copiados, 1 saltados" in logs[-1]
    assert (dest / "Documents" / "a.txt").read_bytes() == b"contenido completo"
