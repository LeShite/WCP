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


def test_locked_destination_does_not_drop_session(env, monkeypatch):
    src, dest, port = env
    for n in ("a.txt", "bad.txt", "z.txt"):
        (src / "Documents" / n).write_bytes(n.encode() * 1000)
    real = os.replace

    def flaky(a, b):
        if str(b).endswith("bad.txt"):
            raise PermissionError("bloqueado por el antivirus")
        return real(a, b)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr("wcp.server.time.sleep", lambda s: None)
    c, logs = send(port)
    assert c.ok and not any("Reconectando" in m for m in logs)
    assert (dest / "Documents" / "a.txt").exists() and (dest / "Documents" / "z.txt").exists()
    assert not (dest / "Documents" / "bad.txt").exists()
    assert any("1 archivos con error" in m for m in logs)


def test_unreadable_source_is_skipped(env):
    src, dest, port = env
    (src / "Documents" / "ok.txt").write_bytes(b"ok")
    locked = src / "Documents" / "locked.txt"
    locked.write_bytes(b"x")
    locked.chmod(0)
    try:
        c, logs = send(port)
    finally:
        locked.chmod(0o600)
    if os.access(locked, os.R_OK) and any("Omitido" not in m for m in logs) and (dest / "Documents" / "locked.txt").exists():
        pytest.skip("se ejecuta como root: chmod no bloquea")
    assert c.ok and (dest / "Documents" / "ok.txt").exists()
    assert any("Omitido" in m for m in logs) and not any("Reconectando" in m for m in logs)


def _conflict_env(env):
    src, dest, port = env
    f = src / "Documents" / "a.txt"
    f.write_bytes(b"version 1")
    assert send(port)[0].ok
    f.write_bytes(b"version 2 distinta")  # ahora difiere del destino
    return f, dest / "Documents" / "a.txt", port


def run_client(port, on_conflict):
    logs = []
    c = SendClient("127.0.0.1", port, "1", ["Documents"], logs.append, lambda *a: None,
                   on_conflict=on_conflict)
    c.run()
    return c, logs


def test_conflict_skip(env):
    f, out, port = _conflict_env(env)
    asked = []
    c, _ = run_client(port, lambda n: asked.append(n) or ("skip", False))
    assert c.ok and asked == ["Documents/a.txt"] and out.read_bytes() == b"version 1"


def test_conflict_overwrite_and_apply_all(env):
    f, out, port = _conflict_env(env)
    c, _ = run_client(port, lambda n: ("overwrite", True))
    assert c.ok and out.read_bytes() == b"version 2 distinta"


def test_conflict_cancel(env):
    f, out, port = _conflict_env(env)
    c, _ = run_client(port, lambda n: ("cancel", False))
    assert not c.ok and out.read_bytes() == b"version 1"


def test_dest_map_routes_each_folder(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "Documents").mkdir(parents=True)
    (src / "Documents" / "a.txt").write_bytes(b"hola")
    monkeypatch.setattr(scanner, "resolve_folder", lambda name: src / name)
    port = next(_ports)
    mapped = tmp_path / "mis_docs"
    srv = ReceiveServer(port, "1", tmp_path / "dest", lambda m: None, lambda *a: None,
                        dest_map={"Documents": str(mapped)})
    srv.start()
    time.sleep(0.5)
    try:
        assert send(port)[0].ok
    finally:
        srv.stop()
        time.sleep(1.2)
    assert (mapped / "a.txt").read_bytes() == b"hola"
    assert not (tmp_path / "dest" / "Documents").exists()


def _server(tmp_path, monkeypatch, **kw):
    src = tmp_path / "src"
    (src / "Documents").mkdir(parents=True, exist_ok=True)
    (src / "Documents" / "a.txt").write_bytes(b"hola mundo")
    monkeypatch.setattr(scanner, "resolve_folder", lambda name: src / name)
    port = next(_ports)
    logs, progs = [], []
    srv = ReceiveServer(port, "1", tmp_path / "dest", logs.append,
                        lambda *a: progs.append(a), **kw)
    srv.start()
    time.sleep(0.5)
    return srv, port, logs, progs


def test_receiver_can_reject(tmp_path, monkeypatch):
    asked = []
    srv, port, logs, _p = _server(tmp_path, monkeypatch,
                                  on_accept=lambda h, ip: asked.append(ip) or False)
    try:
        c, clogs = send(port)
    finally:
        srv.stop()
        time.sleep(1.2)
    assert not c.ok and asked == ["127.0.0.1"]
    assert not (tmp_path / "dest" / "Documents" / "a.txt").exists()
    assert not any("Reconectando" in m for m in clogs)  # rechazo = fin, no reintento


def test_accept_is_remembered_per_ip(tmp_path, monkeypatch):
    asked = []
    srv, port, logs, _p = _server(tmp_path, monkeypatch,
                                  on_accept=lambda h, ip: asked.append(ip) or True)
    try:
        assert send(port)[0].ok and send(port)[0].ok
    finally:
        srv.stop()
        time.sleep(1.2)
    assert asked == ["127.0.0.1"]


def test_receiver_progress_reaches_100(tmp_path, monkeypatch):
    srv, port, logs, progs = _server(tmp_path, monkeypatch)
    try:
        assert send(port)[0].ok
    finally:
        srv.stop()
        time.sleep(1.2)
    pcts = [p[4] for p in progs]
    assert pcts[-1] == 100.0 and all(p is None or 0 <= p <= 100 for p in pcts)


def test_engine_logs_follow_language(tmp_path, monkeypatch):
    from wcp import i18n
    srv, port, logs, _p = _server(tmp_path, monkeypatch)
    i18n.set_lang("en")
    try:
        c, clogs = send(port)
    finally:
        i18n.set_lang("es")
        srv.stop()
        time.sleep(1.2)
    assert c.ok and any("Connected and authenticated" in m for m in clogs)
