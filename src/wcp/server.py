"""Motor de recepción: escucha, autentica y escribe archivos en disco."""
import glob
import json
import os
import socket
import threading
import time
from pathlib import Path
from . import protocol


class ReceiveServer:
    def __init__(self, port, pin, dest_root, on_log, on_progress):
        self.port = int(port)
        self.pin = pin
        self.dest_root = Path(dest_root)
        self.on_log = on_log
        self.on_progress = on_progress
        self._sock = None
        self._broadcaster = None
        self._stop = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._broadcaster = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcaster.start()

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def _broadcast_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({
            "service": "wcp", "port": self.port,
            "hostname": socket.gethostname(),
        }).encode()
        while not self._stop:
            try:
                s.sendto(payload, ("255.255.255.255", protocol.DISCOVERY_PORT))
            except Exception:
                pass
            time.sleep(2.0)
        s.close()

    def _run(self):
        try:
            self.dest_root.mkdir(parents=True, exist_ok=True)
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", self.port))
            srv.listen(1)
            srv.settimeout(1.0)
            self._sock = srv
            self.on_log(f"[OK] Escuchando en puerto {self.port}")
            self.on_log(f"[i] Destino: {self.dest_root}")
            while not self._stop:
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self.on_log(f"[+] Conexión de {addr[0]}")
                try:
                    self._handle(conn, addr)
                except Exception as e:
                    self.on_log(f"[!] Error: {e}")
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception as e:
            self.on_log(f"[ERROR] Servidor: {e}")
        finally:
            try:
                self._sock.close()
            except Exception:
                pass
            self.on_log("[.] Servidor detenido")

    def _handle(self, conn, addr):
        conn.settimeout(protocol.TIMEOUT)
        protocol.set_keepalive(conn)
        magic = protocol.recv_exact(conn, 4)
        if magic != protocol.MAGIC:
            self.on_log("[!] Cliente no-WCP")
            return
        hello = protocol.recv_msg(conn)
        if not hello or hello.get("type") != "hello":
            protocol.send_msg(conn, {"type": "hello_err", "msg": "handshake inválido"})
            return
        if hello.get("pin") != self.pin:
            protocol.send_msg(conn, {"type": "hello_err", "msg": "PIN incorrecto"})
            self.on_log("[!] PIN incorrecto")
            return
        protocol.send_msg(conn, {"type": "hello_ok"})
        self.on_log(f"[OK] Cliente '{hello.get('hostname','?')}' autenticado")

        files_ok = files_skip = 0
        finished = False
        bytes_ok = 0
        t0 = time.time()

        while True:
            msg = protocol.recv_msg(conn)
            if msg is None:
                break
            typ = msg.get("type")
            if typ == "done":
                protocol.send_msg(conn, {"status": "ok"})
                finished = True
                break
            if typ == "dir":
                target = self._target(msg["folder"], msg["relpath"])
                target.mkdir(parents=True, exist_ok=True)
                protocol.send_msg(conn, {"status": "ok"})
                continue
            if typ == "file":
                target = self._target(msg["folder"], msg["relpath"])
                size = int(msg["size"])
                mtime = float(msg.get("mtime", time.time()))
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    st = target.stat()
                    if st.st_size == size and abs(st.st_mtime - mtime) < 2:
                        protocol.send_msg(conn, {"status": "skip"})
                        files_skip += 1
                        continue
                # El parcial lleva size+mtime en el nombre: solo se reanuda
                # si el origen no ha cambiado desde el intento anterior.
                part = target.with_name(
                    f"{target.name}.{size}.{int(mtime * 1000)}.wcp-part")
                for old in target.parent.glob(glob.escape(target.name) + ".*.wcp-part"):
                    if old != part:
                        old.unlink(missing_ok=True)
                offset = part.stat().st_size if part.exists() else 0
                if offset > size:
                    offset = 0
                protocol.send_msg(conn, {
                    "status": "resume" if offset else "ok", "offset": offset})
                try:
                    with open(part, "ab" if offset else "wb") as f:
                        remaining = size - offset
                        while remaining > 0:
                            chunk = protocol.recv_exact(
                                conn, min(protocol.CHUNK, remaining))
                            if chunk is None:
                                raise ConnectionError("conexión cerrada")
                            f.write(chunk)
                            remaining -= len(chunk)
                    os.utime(part, (mtime, mtime))
                    os.replace(part, target)
                    protocol.send_msg(conn, {"status": "ok"})
                    files_ok += 1
                    bytes_ok += size - offset
                    elapsed = max(time.time() - t0, 0.001)
                    self.on_progress(files_ok, files_skip, bytes_ok,
                                     bytes_ok / elapsed)
                except Exception as e:
                    # el parcial se conserva para poder reanudar
                    try:
                        protocol.send_msg(conn, {"status": "error", "msg": str(e)})
                    except Exception:
                        pass
                    raise
                continue

        if not finished:
            self.on_log(f"[!] Conexión perdida: {files_ok} copiados, "
                        f"{files_skip} saltados (el cliente puede reanudar)")
            return
        self.on_log(f"[OK] Sesión: {files_ok} copiados, {files_skip} saltados, "
                    f"{bytes_ok / (1024 * 1024):.1f} MB")

    def _target(self, folder, relpath):
        return self.dest_root / _safe(folder) / _safe(relpath)


def _safe(s):
    s = str(s).replace("\\", "/")
    parts = [p for p in s.split("/") if p not in ("", ".", "..")]
    return Path(*parts) if parts else Path("_")
