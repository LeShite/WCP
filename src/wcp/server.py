"""Motor de recepción: escucha, autentica y escribe archivos en disco."""
import glob
import hashlib
import hmac
import json
import os
import re
import select
import socket
import sys
import threading
import time
from pathlib import Path
from . import protocol
from .i18n import _

MAX_FALLOS = 5      # PIN incorrectos seguidos desde una IP antes de bloquearla
BLOQUEO_SEG = 60


class ReceiveServer:
    def __init__(self, port, pin, dest_root, on_log, on_progress, dest_map=None, on_accept=None):
        self.port = int(port)
        self.pin = pin
        self.dest_root = Path(dest_root)
        # carpeta de origen ("Desktop", ...) -> carpeta destino; el resto va a dest_root/<carpeta>
        self.dest_map = {k: Path(v) for k, v in (dest_map or {}).items() if v}
        # on_accept(hostname, ip) -> bool: el usuario decide; se recuerda por IP mientras el servidor siga activo
        self.on_accept = on_accept
        self._aprobados = set()
        self._fallos = {}  # ip -> [fallos seguidos, bloqueada hasta]
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
            self.on_log(_("[OK] Escuchando en puerto {}").format(self.port))
            self.on_log(_("[i] Destino: {}").format(self.dest_root))
            for name, path in self.dest_map.items():
                self.on_log(f"[i]   {name} -> {path}")
            while not self._stop:
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self.on_log(_("[+] Conexión de {}").format(addr[0]))
                try:
                    self._handle(conn, addr)
                except Exception as e:
                    self.on_log(_("[!] Error: {}: {}").format(type(e).__name__, e))
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception as e:
            self.on_log(_("[ERROR] Servidor: {}").format(e))
        finally:
            try:
                self._sock.close()
            except Exception:
                pass
            self.on_log(_("[.] Servidor detenido"))

    def _handle(self, conn, addr):
        conn.settimeout(protocol.TIMEOUT)
        protocol.tune_socket(conn)
        magic = protocol.recv_exact(conn, 4)
        if magic != protocol.MAGIC:
            self.on_log(_("[!] Cliente no-WCP"))
            return
        hello = protocol.recv_msg(conn)
        if not hello or hello.get("type") != "hello":
            protocol.send_msg(conn, {"type": "hello_err", "msg": "handshake inválido"})
            return
        fallos = self._fallos.setdefault(addr[0], [0, 0.0])
        if time.time() < fallos[1]:  # bloqueada: ni siquiera se comprueba el PIN
            protocol.send_msg(conn, {"type": "hello_err", "msg": "Demasiados intentos, espera un minuto"})
            self.on_log(_("[!] Demasiados intentos desde {}").format(addr[0]))
            return
        if not hmac.compare_digest(str(hello.get("pin")).encode(), self.pin.encode()):
            fallos[0] += 1
            if fallos[0] >= MAX_FALLOS:
                fallos[0], fallos[1] = 0, time.time() + BLOQUEO_SEG
            protocol.send_msg(conn, {"type": "hello_err", "msg": "PIN incorrecto"})
            self.on_log(_("[!] PIN incorrecto"))
            return
        fallos[0] = 0
        nombre = hello.get("hostname", "?")
        if self.on_accept and addr[0] not in self._aprobados:
            gone = threading.Event()  # se activa si el emisor cuelga mientras el usuario decide
            fin = threading.Event()
            threading.Thread(target=self._vigilar, args=(conn, gone, fin), daemon=True).start()
            try:
                aceptado = self.on_accept(nombre, addr[0], gone)
            finally:
                fin.set()
            if gone.is_set():
                self.on_log(_("[!] El emisor canceló la solicitud: {} ({})").format(nombre, addr[0]))
                return
            if not aceptado or self._stop:
                protocol.send_msg(conn, {"type": "hello_err", "msg": "rechazado"})
                self.on_log(_("[!] Envío rechazado: {} ({})").format(nombre, addr[0]))
                return
            self._aprobados.add(addr[0])
        protocol.send_msg(conn, {"type": "hello_ok"})
        self.on_log(_("[OK] Cliente '{}' autenticado").format(nombre))

        files_ok = files_skip = files_fail = 0
        finished = False
        bytes_ok = 0
        pre = 0  # bytes que ya estaban en el destino (saltados o parciales)
        total_bytes = int(hello.get("total_bytes") or 0)  # emisores antiguos no lo envían
        t0 = time.time()

        def progress(final=False):
            if final:
                pct = 100.0
            else:
                pct = min(100.0, 100.0 * (bytes_ok + pre) / total_bytes) if total_bytes else None
            elapsed = max(time.time() - t0, 0.001)
            self.on_progress(files_ok, files_skip, bytes_ok, bytes_ok / elapsed, pct)

        progress()

        while True:
            # keepalive detecta un emisor caído; aquí solo se espera una posible decisión del usuario
            conn.settimeout(protocol.IDLE_TIMEOUT)
            msg = protocol.recv_msg(conn)
            conn.settimeout(protocol.TIMEOUT)
            if msg is None:
                break
            typ = msg.get("type")
            if typ == "done":
                files_skip += int(msg.get("skipped_conflicts", 0))  # omitidos por decisión del usuario
                protocol.send_msg(conn, {"status": "ok", "failed": files_fail})
                finished = True
                break
            if typ == "plan":
                offsets = self._plan(msg)
                files_skip += offsets.count(-1)
                for entry, off in zip(msg["files"], offsets):
                    pre += entry[2] if off == -1 else max(off, 0)
                protocol.send_msg(conn, {"offsets": offsets})
                progress()
                continue
            if typ == "file":
                n = self._recv_file(conn, msg)
                if n is None:
                    files_fail += 1
                    continue
                files_ok += 1
                bytes_ok += n
                progress()
                continue

        if not finished:
            self.on_log(_("[!] Conexión perdida: {} copiados, {} saltados (el cliente puede reanudar)")
                        .format(files_ok, files_skip))
            return
        if files_fail:
            self.on_log(_("[!] {} archivos no se pudieron guardar (ver líneas anteriores)").format(files_fail))
        progress(final=True)
        self.on_log(_("[OK] Sesión: {} copiados, {} saltados, {:.1f} MB")
                    .format(files_ok, files_skip, bytes_ok / (1024 * 1024)))

    @staticmethod
    def _vigilar(conn, gone, fin):
        """Mientras se espera la decisión del usuario el emisor no envía nada: si el socket
        se vuelve legible y vacío, colgó."""
        while not fin.is_set():
            try:
                lectura, _w, _x = select.select([conn], [], [], 0.5)
                if lectura:
                    if conn.recv(1, socket.MSG_PEEK) == b"":
                        gone.set()
                    return
            except (OSError, ValueError):
                gone.set()
                return

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
        for entry in msg["files"]:
            folder, rel, size, mtime = entry[:4]
            digest = entry[4] if len(entry) > 4 else None  # solo con "Verificar contenido"
            target = self._target(folder, rel)
            if target.exists():
                st = target.stat()
                if st.st_size == size and abs(st.st_mtime - mtime) < 2:
                    if digest and _sha256(target) != digest:
                        # mismo tamaño y fecha pero otro contenido: está dañado, se rehace sin preguntar
                        self.on_log(_("[i] Archivo dañado, se reconstruye: {}").format(rel))
                        offsets.append(0)
                        continue
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
            self.on_log(_("[!] No se pudo guardar {}: {}: {}").format(rel, type(err).__name__, err))
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


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(protocol.CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _safe(s):
    s = str(s).replace("\\", "/")
    # sin ":" (unidad "C:") ni otros caracteres inválidos en Windows: una ruta con unidad
    # reemplazaría la carpeta destino al unirla
    parts = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p).rstrip(". ") for p in s.split("/")]
    parts = [p for p in parts if p]
    return Path(*parts) if parts else Path("_")
