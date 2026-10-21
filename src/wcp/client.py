"""Motor de envío: escanea, conecta y empuja archivos al servidor."""
import socket
import time
from . import protocol
from .i18n import _
from .scanner import walk


MAX_RETRIES = 5
BATCH = 2000  # archivos por plan: un viaje de ida y vuelta por lote, no por archivo


class SendClient:
    def __init__(self, host, port, pin, folders, on_log, on_progress, on_conflict=None):
        self.host = host
        self.port = int(port)
        self.pin = pin
        self.folders = folders
        self.on_log = on_log
        self.on_progress = on_progress
        # on_conflict(nombre) -> ("skip"|"overwrite"|"cancel", aplicar_a_todos); sin él se sobrescribe
        self.on_conflict = on_conflict
        self._decisions = {}
        self._all = None
        self.ok = False
        self._stop = False
        self._sent = 0
        self._sock = None

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                self._sock.close()  # desbloquea una espera larga (p. ej. confirmación del receptor)
        except OSError:
            pass

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
                    self.on_log(_("[~] Conexión perdida ({}). Reconectando ({}/{})...")
                                .format(e, failures + 1, MAX_RETRIES))
                    self._wait(min(2 ** failures, 15))
        except Exception as e:
            self.on_log(_("[ERROR] {}").format(e))

    def _decide(self, label, rel):
        key = (label, _norm(rel))
        if self._all:
            return self._all
        if key not in self._decisions:  # se recuerda: una reconexión no vuelve a preguntar
            choice, apply_all = ("overwrite", False)
            if self.on_conflict:
                choice, apply_all = self.on_conflict(f"{label}/{key[1]}")
            if choice == "cancel":
                raise RuntimeError(_("cancelado por el usuario"))
            if apply_all:
                self._all = choice
            self._decisions[key] = choice
        return self._decisions[key]

    def _wait(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if self._stop:
                raise RuntimeError(_("cancelado por el usuario"))
            time.sleep(0.2)

    def _recv(self, sock):
        resp = protocol.recv_msg(sock)
        if resp is None:
            raise ConnectionError(_("el receptor cerró la conexión"))
        return resp

    def _session(self, items):
        self.on_log(_("Conectando a {}:{}...").format(self.host, self.port))
        total_files = sum(1 for it in items if it[0] == "file")
        total_bytes = sum(it[5] for it in items if it[0] == "file")
        sock = socket.create_connection((self.host, self.port), timeout=15)
        self._sock = sock
        sock.settimeout(protocol.TIMEOUT)
        protocol.tune_socket(sock)
        try:
            sock.sendall(protocol.MAGIC)
            protocol.send_msg(sock, {"type": "hello", "pin": self.pin,
                                     "hostname": socket.gethostname(),
                                     "total_files": total_files, "total_bytes": total_bytes})
            sock.settimeout(protocol.IDLE_TIMEOUT)  # el receptor puede estar pidiendo confirmación
            resp = self._recv(sock)
            sock.settimeout(protocol.TIMEOUT)
            if resp.get("type") != "hello_ok":
                if resp.get("msg") == "rechazado":
                    raise RuntimeError(_("El receptor rechazó la conexión"))
                raise RuntimeError(_("Handshake fallido: {}").format(_(resp.get("msg", "sin respuesta"))))
            self.on_log(_("[OK] Conectado y autenticado"))

            self.on_log(_("Enviando {} archivos ({})").format(total_files, _human(total_bytes)))

            done = 0
            done_bytes = 0
            copied = skipped = failed = 0
            t0 = time.time()

            def progress():
                self.on_progress(done, total_files, done_bytes, total_bytes,
                                 self._sent / max(time.time() - t0, 0.001))

            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                files = [it for it in batch if it[0] == "file"]
                protocol.send_msg(sock, {
                    "type": "plan",
                    "dirs": [[it[1], _norm(it[3])] for it in batch if it[0] == "dir"],
                    "files": [[it[1], _norm(it[3]), it[5], it[6]] for it in files],
                })
                offsets = self._recv(sock).get("offsets")
                if not isinstance(offsets, list) or len(offsets) != len(files):
                    raise RuntimeError(_("plan inválido del receptor"))

                # el receptor ya dijo qué falta: se envía todo seguido, sin esperar acuses
                for (kind, label, root, rel, path, size, mtime), offset in zip(files, offsets):
                    if self._stop:
                        raise RuntimeError(_("cancelado por el usuario"))
                    if offset == -2:  # existe y es distinto en el destino
                        offset = -1 if self._decide(label, rel) == "skip" else 0
                    if offset == -1:
                        skipped += 1
                        done += 1
                        done_bytes += size
                        continue
                    if not 0 <= offset <= size:
                        raise RuntimeError(_("offset inválido del receptor para {}").format(rel))
                    try:
                        f = open(path, "rb")
                    except OSError as e:
                        # bloqueado/ilegible: se avisa y se sigue, no es un corte de red
                        self.on_log(_("[!] Omitido {}: {}").format(rel, e))
                        failed += 1
                        done += 1
                        continue
                    with f:
                        protocol.send_msg(sock, {
                            "type": "file", "folder": label, "relpath": _norm(rel),
                            "size": size, "mtime": mtime, "offset": offset,
                        })
                        if offset:
                            f.seek(offset)
                            self.on_log(_("[i] Reanudando {} desde {}").format(rel, _human(offset)))
                        remaining = size - offset
                        while remaining > 0:
                            if self._stop:
                                raise RuntimeError(_("cancelado por el usuario"))
                            chunk = f.read(min(protocol.CHUNK, remaining))
                            if not chunk:
                                raise RuntimeError(_("archivo modificado durante el envío: {}").format(path))
                            sock.sendall(chunk)
                            self._sent += len(chunk)
                            remaining -= len(chunk)
                    copied += 1
                    done += 1
                    done_bytes += size
                    progress()
                progress()

            # el acuse final confirma que el receptor guardó todo
            protocol.send_msg(sock, {"type": "done"})
            ack = self._recv(sock)
            if ack.get("status") != "ok":
                raise ConnectionError(_("el receptor no confirmó la recepción"))
            failed += int(ack.get("failed", 0))
            self.on_log(_("[OK] Terminado: {} copiados, {} saltados")
                        .format(copied - int(ack.get("failed", 0)), skipped))
            if failed:
                self.on_log(_("[!] {} archivos con error: pulsa Iniciar de nuevo para reintentarlos (detalle en el registro del receptor)").format(failed))
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
