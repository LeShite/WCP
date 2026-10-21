"""Motor de recepción: escucha, autentica y escribe archivos en disco."""
import glob
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from . import protocol


class ReceiveServer:
    def __init__(self, port, pin, dest_root, on_log, on_progress, dest_map=None):
        self.port = int(port)
        self.pin = pin
        self.dest_root = Path(dest_root)
        # carpeta de origen ("Desktop", ...) -> carpeta destino; el resto va a dest_root/<carpeta>
        self.dest_map = {k: Path(v) for k, v in (dest_map or {}).items() if v}
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
            for name, path in self.dest_map.items():
                self.on_log(f"[i]   {name} -> {path}")
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
                    self.on_log(f"[!] Error: {type(e).__name__}: {e}")
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
        protocol.tune_socket(conn)
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

        files_ok = files_skip = files_fail = 0
        finished = False
        bytes_ok = 0
        t0 = time.time()

        while True:
            # keepalive detecta un emisor caído; aquí solo se espera una posible decisión del usuario
            conn.settimeout(protocol.IDLE_TIMEOUT)
            msg = protocol.recv_msg(conn)
            conn.settimeout(protocol.TIMEOUT)
            if msg is None:
                break
            typ = msg.get("type")
            if typ == "done":
                protocol.send_msg(conn, {"status": "ok", "failed": files_fail})
                finished = True
                break
            if typ == "plan":
                offsets = self._plan(msg)
                files_skip += offsets.count(-1)
                protocol.send_msg(conn, {"offsets": offsets})
                continue
            if typ == "file":
                n = self._recv_file(conn, msg)
                if n is None:
                    files_fail += 1
                    continue
                files_ok += 1
                bytes_ok += n
                elapsed = max(time.time() - t0, 0.001)
                self.on_progress(files_ok, files_skip, bytes_ok, bytes_ok / elapsed)
                continue

        if not finished:
            self.on_log(f"[!] Conexión perdida: {files_ok} copiados, "
                        f"{files_skip} saltados (el cliente puede reanudar)")
            return
        if files_fail:
            self.on_log(f"[!] {files_fail} archivos no se pudieron guardar (ver líneas anteriores)")
        self.on_log(f"[OK] Sesión: {files_ok} copiados, {files_skip} saltados, "
                    f"{bytes_ok / (1024 * 1024):.1f} MB")

    @staticmethod
    def _part(target, size, mtime):
        # size+mtime en el nombre: solo se reanuda si el origen no ha cambiado
        return target.with_name(f"{target.name}.{size}.{int(mtime * 1000)}.wcp-part")

    def _plan(self, msg):
        """Por archivo: -1 = ya está completo; -2 = existe y es distinto (decide el
        emisor); n >= 0 = enviar desde el byte n."""
        for folder, rel in msg.get("dirs", []):
            self._target(folder, rel).mkdir(parents=True, exist_ok=True)
        offsets = []
        for folder, rel, size, mtime in msg["files"]:
            target = self._target(folder, rel)
            if target.exists():
                st = target.stat()
                if st.st_size == size and abs(st.st_mtime - mtime) < 2:
                    offsets.append(-1)
                    continue
                offsets.append(-2)
                continue
            part = self._part(target, size, mtime)
            if target.parent.is_dir():
                for old in target.parent.glob(glob.escape(target.name) + ".*.wcp-part"):
                    if old != part:
                        old.unlink(missing_ok=True)
            off = part.stat().st_size if part.exists() else 0
            offsets.append(off if off <= size else 0)
        return offsets

    def _recv_file(self, conn, msg):
        """Devuelve los bytes recibidos, o None si el archivo no se pudo guardar.

        Un fallo local (antivirus, archivo bloqueado, ruta larga) no corta la
        sesión: se consumen los datos para mantener el flujo y se sigue.
        """
        rel = msg["relpath"]
        size = int(msg["size"])
        mtime = float(msg["mtime"])
        offset = int(msg["offset"])
        err = None
        f = None
        try:
            target = self._target(msg["folder"], rel)
            part = self._part(target, size, mtime)
            target.parent.mkdir(parents=True, exist_ok=True)
            if offset and (not part.exists() or part.stat().st_size != offset):
                raise ValueError("parcial inconsistente")
            f = open(part, "ab" if offset else "wb")
        except Exception as e:
            err = e
        remaining = size - offset
        while remaining > 0:
            chunk = protocol.recv_exact(conn, min(protocol.CHUNK, remaining))
            if chunk is None:
                if f:
                    f.close()  # el parcial se conserva para reanudar
                raise ConnectionError("conexión cerrada")
            remaining -= len(chunk)
            if f:
                try:
                    f.write(chunk)
                except OSError as e:
                    err = e
                    f.close()
                    f = None
        if f:
            f.close()
            try:
                os.utime(part, (mtime, mtime))
                self._replace(part, target)
            except Exception as e:
                err = e
        if err:
            self.on_log(f"[!] No se pudo guardar {rel}: {type(err).__name__}: {err}")
            return None
        return size - offset

    @staticmethod
    def _replace(part, target):
        # En Windows el antivirus puede tener el archivo abierto un instante, y un
        # destino oculto/de solo lectura (p. ej. desktop.ini) rechaza el reemplazo.
        for attempt in range(4):
            try:
                if sys.platform == "win32" and target.exists():
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(target), 0x80)
                os.replace(part, target)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.3)

    def _target(self, folder, relpath):
        base = self.dest_map.get(folder) or self.dest_root / _safe(folder)
        return base / _safe(relpath)


def _safe(s):
    s = str(s).replace("\\", "/")
    parts = [p for p in s.split("/") if p not in ("", ".", "..")]
    return Path(*parts) if parts else Path("_")
