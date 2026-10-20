"""Motor de envío: escanea, conecta y empuja archivos al servidor."""
import socket
import time
from . import protocol
from .scanner import walk


MAX_RETRIES = 5


class SendClient:
    def __init__(self, host, port, pin, folders, on_log, on_progress):
        self.host = host
        self.port = int(port)
        self.pin = pin
        self.folders = folders
        self.on_log = on_log
        self.on_progress = on_progress
        self.ok = False
        self._stop = False
        self._sent = 0

    def stop(self):
        self._stop = True

    def run(self):
        try:
            items = list(walk(self.folders, on_log=self.on_log))
            failures = 0
            while True:
                self._sent = 0
                try:
                    self._session(items)
                    self.ok = True
                    return
                except (OSError, ConnectionError) as e:
                    # avanzar algo en este intento reinicia el contador
                    failures = 0 if self._sent else failures + 1
                    if failures >= MAX_RETRIES:
                        raise
                    self.on_log(f"[~] Conexión perdida ({e}). "
                                f"Reconectando ({failures + 1}/{MAX_RETRIES})...")
                    self._wait(min(2 ** failures, 15))
        except Exception as e:
            self.on_log(f"[ERROR] {e}")

    def _wait(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if self._stop:
                raise RuntimeError("cancelado por el usuario")
            time.sleep(0.2)

    def _recv(self, sock):
        resp = protocol.recv_msg(sock)
        if resp is None:
            raise ConnectionError("el receptor cerró la conexión")
        return resp

    def _session(self, items):
        self.on_log(f"Conectando a {self.host}:{self.port}...")
        sock = socket.create_connection((self.host, self.port), timeout=15)
        sock.settimeout(protocol.TIMEOUT)
        protocol.set_keepalive(sock)
        try:
            sock.sendall(protocol.MAGIC)
            protocol.send_msg(sock, {"type": "hello", "pin": self.pin,
                                     "hostname": socket.gethostname()})
            resp = self._recv(sock)
            if resp.get("type") != "hello_ok":
                raise RuntimeError(f"Handshake fallido: {resp.get('msg', 'sin respuesta')}")
            self.on_log("[OK] Conectado y autenticado")

            total_files = sum(1 for it in items if it[0] == "file")
            total_bytes = sum(it[5] for it in items if it[0] == "file")
            self.on_log(f"Enviando {total_files} archivos ({_human(total_bytes)})")

            done = 0
            done_bytes = 0
            copied = skipped = 0
            t0 = time.time()

            for kind, label, root, rel, path, size, mtime in items:
                if self._stop:
                    raise RuntimeError("cancelado por el usuario")
                if kind == "dir":
                    protocol.send_msg(sock, {"type": "dir", "folder": label,
                                             "relpath": _norm(rel)})
                    self._recv(sock)
                    continue

                protocol.send_msg(sock, {
                    "type": "file", "folder": label, "relpath": _norm(rel),
                    "size": size, "mtime": mtime,
                })
                # el receptor decide: skip / ok (desde 0) / resume (desde offset)
                resp = self._recv(sock)
                status = resp.get("status", "error")
                offset = int(resp.get("offset", 0))
                if status == "error":
                    self.on_log(f"[!] Error en {rel}: {resp.get('msg')}")
                    done += 1
                    continue
                if status == "skip":
                    skipped += 1
                    done += 1
                    done_bytes += size
                    self.on_progress(done, total_files, done_bytes, total_bytes,
                                     self._sent / max(time.time() - t0, 0.001))
                    continue
                if not 0 <= offset <= size:
                    raise RuntimeError(f"offset inválido del receptor para {rel}")

                with open(path, "rb") as f:
                    if offset:
                        f.seek(offset)
                        self.on_log(f"[i] Reanudando {rel} desde {_human(offset)}")
                    remaining = size - offset
                    while remaining > 0:
                        if self._stop:
                            raise RuntimeError("cancelado por el usuario")
                        chunk = f.read(min(protocol.CHUNK, remaining))
                        if not chunk:
                            raise RuntimeError(f"archivo truncado: {path}")
                        sock.sendall(chunk)
                        self._sent += len(chunk)
                        remaining -= len(chunk)

                if self._recv(sock).get("status") == "ok":
                    copied += 1
                    done_bytes += size
                else:
                    self.on_log(f"[!] Error guardando {rel}")
                done += 1
                self.on_progress(done, total_files, done_bytes, total_bytes,
                                 self._sent / max(time.time() - t0, 0.001))

            protocol.send_msg(sock, {"type": "done"})
            try:
                protocol.recv_msg(sock)
            except Exception:
                pass
            self.on_log(f"[OK] Terminado: {copied} copiados, {skipped} saltados")
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
