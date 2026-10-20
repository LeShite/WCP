"""Motor de envío: escanea, conecta y empuja archivos al servidor."""
import socket
import time
from . import protocol
from .scanner import walk


class SendClient:
    def __init__(self, host, port, pin, folders, on_log, on_progress):
        self.host = host
        self.port = int(port)
        self.pin = pin
        self.folders = folders
        self.on_log = on_log
        self.on_progress = on_progress
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.on_log(f"[ERROR] {e}")

    def _run(self):
        self.on_log(f"Conectando a {self.host}:{self.port}...")
        sock = socket.create_connection((self.host, self.port), timeout=15)
        sock.settimeout(120)
        try:
            sock.sendall(protocol.MAGIC)
            protocol.send_msg(sock, {"type": "hello", "pin": self.pin,
                                     "hostname": socket.gethostname()})
            resp = protocol.recv_msg(sock)
            if not resp or resp.get("type") != "hello_ok":
                msg = (resp or {}).get("msg", "sin respuesta")
                raise RuntimeError(f"Handshake fallido: {msg}")
            self.on_log("[OK] Conectado y autenticado")

            items = list(walk(self.folders, on_log=self.on_log))
            total_files = sum(1 for it in items if it[0] == "file")
            total_bytes = sum(it[5] for it in items if it[0] == "file")
            self.on_log(f"Enviando {total_files} archivos ({_human(total_bytes)})")

            done = 0
            done_bytes = 0
            skipped = 0
            t0 = time.time()

            for kind, label, root, rel, path, size, mtime in items:
                if self._stop:
                    raise RuntimeError("cancelado por el usuario")
                if kind == "dir":
                    protocol.send_msg(sock, {"type": "dir", "folder": label,
                                             "relpath": _norm(rel)})
                    protocol.recv_msg(sock)
                    continue

                protocol.send_msg(sock, {
                    "type": "file", "folder": label, "relpath": _norm(rel),
                    "size": size, "mtime": mtime,
                })
                with open(path, "rb") as f:
                    remaining = size
                    while remaining > 0:
                        if self._stop:
                            raise RuntimeError("cancelado por el usuario")
                        chunk = f.read(min(protocol.CHUNK, remaining))
                        if not chunk:
                            raise IOError(f"archivo truncado: {path}")
                        sock.sendall(chunk)
                        remaining -= len(chunk)

                resp = protocol.recv_msg(sock)
                status = (resp or {}).get("status", "error")
                if status == "skip":
                    skipped += 1
                elif status == "ok":
                    done_bytes += size
                else:
                    self.on_log(f"[!] Error en {rel}: {(resp or {}).get('msg')}")
                done += 1

                elapsed = max(time.time() - t0, 0.001)
                self.on_progress(done, total_files, done_bytes, total_bytes,
                                 done_bytes / elapsed)

            protocol.send_msg(sock, {"type": "done"})
            try:
                protocol.recv_msg(sock)
            except Exception:
                pass
            self.on_log(f"[OK] Terminado: {done - skipped} copiados, {skipped} saltados")
        finally:
            try:
                sock.close()
            except Exception:
                pass


def _norm(p):
    return str(p).replace("\\", "/")


def _human(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
