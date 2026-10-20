"""Interfaz Tkinter para WCP."""
import queue
import random
import socket
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from . import APP_NAME, protocol
from .client import SendClient
from .scanner import FOLDERS, resolve_folder
from .server import ReceiveServer

FOLDER_LABELS = {
    "Desktop": "Escritorio",
    "Documents": "Documentos",
    "Downloads": "Descargas",
    "Pictures": "Fotos / Imágenes",
}


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips or ["(no detectada)"]


def discover(timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", protocol.DISCOVERY_PORT))
    except OSError:
        return {}
    s.settimeout(0.5)
    found = {}
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(1024)
            import json
            obj = json.loads(data.decode("utf-8"))
            if obj.get("service") == "wcp":
                found[addr[0]] = obj
        except socket.timeout:
            continue
        except Exception:
            continue
    s.close()
    return found


def _human(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("820x680")
        root.minsize(760, 600)

        self.send_q = queue.Queue()
        self.recv_q = queue.Queue()
        self.state = {
            "send": {"pct": 0, "text": "Listo"},
            "recv": {"text": "Listo"},
        }
        self.server = None
        self.client = None
        self._closing = False

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self.tab_send = ttk.Frame(notebook)
        self.tab_recv = ttk.Frame(notebook)
        notebook.add(self.tab_send, text="  Enviar  ")
        notebook.add(self.tab_recv, text="  Recibir  ")

        self._build_send()
        self._build_recv()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # ---------- ENVIAR ----------
    def _build_send(self):
        f = self.tab_send

        cf = ttk.LabelFrame(f, text="Destino")
        cf.pack(fill="x", padx=8, pady=6)

        ttk.Label(cf, text="IP / host:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.host_var = tk.StringVar()
        ttk.Entry(cf, textvariable=self.host_var, width=22).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(cf, text="Buscar", width=8, command=self._do_discover).grid(row=0, column=2, padx=4)

        ttk.Label(cf, text="Puerto:").grid(row=0, column=3, padx=4)
        self.port_var_s = tk.StringVar(value=str(protocol.DEFAULT_PORT))
        ttk.Entry(cf, textvariable=self.port_var_s, width=8).grid(row=0, column=4, padx=4)

        ttk.Label(cf, text="PIN:").grid(row=0, column=5, padx=4)
        self.pin_var_s = tk.StringVar()
        ttk.Entry(cf, textvariable=self.pin_var_s, width=10).grid(row=0, column=6, padx=4)

        ff = ttk.LabelFrame(f, text="Carpetas")
        ff.pack(fill="x", padx=8, pady=6)
        self.folder_vars = {}
        for i, name in enumerate(FOLDERS):
            var = tk.BooleanVar(value=True)
            self.folder_vars[name] = var
            path = resolve_folder(name)
            estado = "OK" if path.is_dir() else "NO EXISTE"
            ttk.Checkbutton(
                ff,
                text=f"{FOLDER_LABELS.get(name, name):18s}  {path}   [{estado}]",
                variable=var,
            ).grid(row=i, column=0, sticky="w", padx=4, pady=2)

        bf = ttk.Frame(f)
        bf.pack(fill="x", padx=8, pady=6)
        self.btn_send = ttk.Button(bf, text="▶  Iniciar envío", command=self._start_send)
        self.btn_send.pack(side="left")
        self.btn_send_stop = ttk.Button(bf, text="■  Detener", state="disabled",
                                        command=self._stop_send)
        self.btn_send_stop.pack(side="left", padx=6)

        self.prog_s = ttk.Progressbar(f, mode="determinate", maximum=100)
        self.prog_s.pack(fill="x", padx=8, pady=(4, 2))
        self.status_s = tk.StringVar(value="Listo")
        ttk.Label(f, textvariable=self.status_s).pack(anchor="w", padx=8)

        lf = ttk.LabelFrame(f, text="Registro")
        lf.pack(fill="both", expand=True, padx=8, pady=6)
        self.send_log = tk.Text(lf, height=8, state="disabled", bg="#111", fg="#7CFC00",
                                font=("Consolas", 9), wrap="word")
        self.send_log.pack(fill="both", expand=True)

    # ---------- RECIBIR ----------
    def _build_recv(self):
        f = self.tab_recv

        inf = ttk.LabelFrame(f, text="Tu PC (comparte estos datos con el origen)")
        inf.pack(fill="x", padx=8, pady=6)
        ips = ", ".join(local_ips())
        ttk.Label(inf, text=f"IP: {ips}", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=6, pady=2)

        row = ttk.Frame(inf)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="Puerto:").pack(side="left")
        self.port_var_r = tk.StringVar(value=str(protocol.DEFAULT_PORT))
        ttk.Entry(row, textvariable=self.port_var_r, width=8).pack(side="left", padx=4)
        ttk.Label(row, text="PIN:").pack(side="left", padx=(12, 0))
        self.pin_var_r = tk.StringVar(value=f"{random.randint(100000, 999999)}")
        ttk.Entry(row, textvariable=self.pin_var_r, width=10).pack(side="left", padx=4)
        ttk.Button(row, text="↻", width=3, command=self._new_pin).pack(side="left")

        df = ttk.LabelFrame(f, text="Carpeta destino")
        df.pack(fill="x", padx=8, pady=6)
        self.dest_var = tk.StringVar(value=str(Path.home()))
        ttk.Entry(df, textvariable=self.dest_var).pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(df, text="...", width=4, command=self._pick_dest).pack(side="left", padx=4)

        bf = ttk.Frame(f)
        bf.pack(fill="x", padx=8, pady=6)
        self.btn_recv = ttk.Button(bf, text="▶  Iniciar recepción", command=self._start_recv)
        self.btn_recv.pack(side="left")
        self.btn_recv_stop = ttk.Button(bf, text="■  Detener", state="disabled",
                                        command=self._stop_recv)
        self.btn_recv_stop.pack(side="left", padx=6)

        self.status_r = tk.StringVar(value="Detenido")
        ttk.Label(f, textvariable=self.status_r).pack(anchor="w", padx=8)

        lf = ttk.LabelFrame(f, text="Registro")
        lf.pack(fill="both", expand=True, padx=8, pady=6)
        self.recv_log = tk.Text(lf, height=10, state="disabled", bg="#111", fg="#7CFC00",
                                font=("Consolas", 9), wrap="word")
        self.recv_log.pack(fill="both", expand=True)

    # ---------- Helpers UI ----------
    def _new_pin(self):
        self.pin_var_r.set(f"{random.randint(100000, 999999)}")

    def _pick_dest(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(initialdir=self.dest_var.get() or str(Path.home()))
        if p:
            self.dest_var.set(p)

    def _write_log(self, text_widget, msg):
        text_widget.configure(state="normal")
        text_widget.insert("end", msg + "\n")
        text_widget.see("end")
        text_widget.configure(state="disabled")

    def _poll(self):
        if self._closing:
            return
        try:
            while True:
                msg = self.send_q.get_nowait()
                self._write_log(self.send_log, msg)
        except queue.Empty:
            pass
        try:
            while True:
                msg = self.recv_q.get_nowait()
                self._write_log(self.recv_log, msg)
        except queue.Empty:
            pass

        s = self.state["send"]
        self.prog_s.configure(value=s["pct"])
        self.status_s.set(s["text"])
        self.status_r.set(self.state["recv"]["text"])

        self.root.after(120, self._poll)

    # ---------- ENVIAR acciones ----------
    def _do_discover(self):
        self.send_q.put("[i] Buscando servidores WCP en la red (2s)...")
        def worker():
            found = discover(2.5)
            if not found:
                self.send_q.put("[!] No se encontraron servidores")
                return
            first = next(iter(found))
            self.send_q.put(f"[OK] Encontrados: {', '.join(found)}")
            def set_host():
                self.host_var.set(first)
                self.port_var_s.set(str(found[first].get("port", protocol.DEFAULT_PORT)))
            self.root.after(0, set_host)
        threading.Thread(target=worker, daemon=True).start()

    def _start_send(self):
        if self.client is not None:
            return
        host = self.host_var.get().strip()
        pin = self.pin_var_s.get().strip()
        if not host or not pin:
            messagebox.showwarning("WCP", "Completa IP y PIN")
            return
        folders = [f for f, v in self.folder_vars.items() if v.get()]
        if not folders:
            messagebox.showwarning("WCP", "Selecciona al menos una carpeta")
            return
        try:
            port = int(self.port_var_s.get())
        except ValueError:
            messagebox.showerror("WCP", "Puerto inválido")
            return

        self.btn_send.configure(state="disabled")
        self.btn_send_stop.configure(state="normal")
        self.state["send"] = {"pct": 0, "text": "Conectando..."}

        def log(m):
            self.send_q.put(m)
            if m.startswith("[~]"):  # reconexión: visible también en la barra de estado
                self.state["send"]["text"] = m[4:]
        def prog(done, total, db, tb, rate):
            self.state["send"]["pct"] = 100.0 * db / max(tb, 1)
            self.state["send"]["text"] = (
                f"{done}/{total} archivos · {_human(db)}/{_human(tb)} · "
                f"{_human(int(rate))}/s"
            )

        self.client = SendClient(host, port, pin, folders, log, prog)

        def runner():
            try:
                self.client.run()
            finally:
                self.root.after(0, self._send_done)

        threading.Thread(target=runner, daemon=True).start()

    def _send_done(self):
        ok = self.client.ok
        self.client = None
        self.btn_send.configure(state="normal")
        self.btn_send_stop.configure(state="disabled")
        if ok:
            self.state["send"]["pct"] = 100
            self.state["send"]["text"] = "Completado ✔"
        else:
            self.state["send"]["text"] = "Interrumpido — pulsa Iniciar para reanudar"

    def _stop_send(self):
        if self.client:
            self.client.stop()
            self.send_q.put("[!] Deteniendo...")

    # ---------- RECIBIR acciones ----------
    def _start_recv(self):
        if self.server is not None:
            return
        pin = self.pin_var_r.get().strip()
        dest = self.dest_var.get().strip()
        try:
            port = int(self.port_var_r.get())
        except ValueError:
            messagebox.showerror("WCP", "Puerto inválido")
            return
        if not dest:
            messagebox.showerror("WCP", "Elige carpeta destino")
            return

        def log(m): self.recv_q.put(m)
        def prog(ok, skip, b, rate):
            self.state["recv"]["text"] = (
                f"Recibidos: {ok} · Saltados: {skip} · {_human(b)} · {_human(int(rate))}/s"
            )

        self.server = ReceiveServer(port, pin, dest, log, prog)
        self.server.start()
        self.btn_recv.configure(state="disabled")
        self.btn_recv_stop.configure(state="normal")
        self.state["recv"]["text"] = "Escuchando..."

    def _stop_recv(self):
        if self.server:
            self.server.stop()
            self.server = None
        self.btn_recv.configure(state="normal")
        self.btn_recv_stop.configure(state="disabled")
        self.state["recv"]["text"] = "Detenido"

    def _on_close(self):
        self._closing = True
        try:
            if self.server:
                self.server.stop()
            if self.client:
                self.client.stop()
        finally:
            self.root.destroy()
