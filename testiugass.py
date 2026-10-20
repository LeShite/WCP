"""Interfaz Liquid Glass para WCP usando PyQt6."""
import queue
import random
import socket
import threading
import time
import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QGraphicsDropShadowEffect,
                             QLineEdit, QCheckBox, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
                             QStackedWidget)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, QPoint, QTimer
from PyQt6.QtGui import QColor, QFont, QCursor

# Importaciones de tu motor (asegúrate de que las rutas sean correctas)
try:
    from . import APP_NAME, protocol
    from .client import SendClient
    from .scanner import FOLDERS, resolve_folder
    from .server import ReceiveServer
except ImportError:
    # Fallback para pruebas aisladas si no encuentra el paquete
    APP_NAME = "WCP - Windows Copy Peer"
    protocol = type('protocol', (), {'DEFAULT_PORT': 8765, 'DISCOVERY_PORT': 8766})
    FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures"]
    resolve_folder = lambda x: Path.home() / x
    SendClient = None
    ReceiveServer = None

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
    import json
    while time.time() < end:
        try:
            data, addr = s.recvfrom(1024)
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

class WCPWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(820, 750)
        
        # Configuración de ventana sin bordes (Liquid Glass)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("QMainWindow { background: transparent; }")

        # Variables de estado (igual que en Tkinter)
        self.send_q = queue.Queue()
        self.recv_q = queue.Queue()
        self.state = {
            "send": {"pct": 0, "text": "Listo"},
            "recv": {"text": "Listo"},
        }
        self.server = None
        self.client = None
        self._closing = False
        self.old_pos = None

        self._setup_ui()
        self._poll() # Iniciar el bucle de actualización de UI

    def _setup_ui(self):
        # Panel de cristal
        self.glass = QWidget(self)
        self.glass.setGeometry(20, 20, 780, 710)
        
        self.base_style = """
            QWidget {
                background-color: rgba(18, 18, 24, 245);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 30);
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel { border: none; background: transparent; }
            QLineEdit {
                background-color: rgba(255, 255, 255, 10); border: 1px solid rgba(255, 255, 255, 30);
                color: white; border-radius: 8px; padding: 6px;
            }
            QCheckBox { background: transparent; padding: 4px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; }
            QCheckBox::indicator:unchecked { background-color: #313244; border: 2px solid #45475a; }
            QCheckBox::indicator:checked { background-color: #89b4fa; border: 2px solid #89b4fa; }
            QPushButton {
                background-color: #89b4fa; color: #11111b; border-radius: 8px;
                font-weight: bold; font-size: 13px; padding: 8px; border: none;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; color: #7f849c; }
            QProgressBar {
                background-color: #313244; border-radius: 6px; text-align: center;
                color: white; font-weight: bold; height: 20px;
            }
            QProgressBar::chunk { background-color: #89b4fa; border-radius: 6px; }
            QTextEdit { 
                background-color: #11111b; color: #a6e3a1; font-family: Consolas, monospace;
                border: 1px solid #313244; border-radius: 8px; padding: 5px;
            }
            QPushButton#TabButton {
                background-color: transparent; color: #7f849c; border-radius: 0px;
                border-bottom: 3px solid transparent; font-size: 16px; padding: 10px;
            }
            QPushButton#TabButton:hover { color: #cdd6f4; }
            QPushButton#TabButton:checked { 
                color: #89b4fa; border-bottom: 3px solid #89b4fa; font-weight: bold;
            }
        """
        self.glass.setStyleSheet(self.base_style)

        # Sombra
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 10)
        self.glass.setGraphicsEffect(shadow)

        # Layout principal del cristal
        main_layout = QVBoxLayout(self.glass)
        main_layout.setContentsMargins(20, 10, 20, 20)
        main_layout.setSpacing(10)

        # Barra de arrastre superior
        drag_bar = QWidget()
        drag_bar.setFixedHeight(30)
        drag_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        drag_layout = QHBoxLayout(drag_bar)
        drag_layout.setContentsMargins(0, 0, 0, 0)
        
        btn_close = QPushButton("✖")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("background: transparent; color: #f38ba8; font-size: 16px;")
        btn_close.clicked.connect(self._on_close)
        
        drag_layout.addStretch()
        drag_layout.addWidget(btn_close)
        main_layout.addWidget(drag_bar)

        # Pestañas
        tab_bar = QHBoxLayout()
        self.btn_tab_send = QPushButton("Enviar")
        self.btn_tab_send.setObjectName("TabButton")
        self.btn_tab_send.setCheckable(True)
        self.btn_tab_send.setChecked(True)
        self.btn_tab_send.clicked.connect(lambda: self._switch_tab(0))
        
        self.btn_tab_recv = QPushButton("Recibir")
        self.btn_tab_recv.setObjectName("TabButton")
        self.btn_tab_recv.setCheckable(True)
        self.btn_tab_recv.clicked.connect(lambda: self._switch_tab(1))
        
        tab_bar.addWidget(self.btn_tab_send)
        tab_bar.addWidget(self.btn_tab_recv)
        tab_bar.addStretch()
        main_layout.addLayout(tab_bar)

        # Stacked Widget para cambiar vistas
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self.view_send = self._build_send_view()
        self.view_recv = self._build_recv_view()
        self.stack.addWidget(self.view_send)
        self.stack.addWidget(self.view_recv)

        # Animación de entrada
        self._animate_entrance()
        self.drag_bar = drag_bar # Referencia para el mousePressEvent

    def _build_send_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 1. Destino (IP, Puerto, PIN, Buscar)
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("IP / host:"))
        self.host_input = QLineEdit()
        self.host_input.setFixedWidth(180)
        conn_layout.addWidget(self.host_input)
        
        self.btn_search = QPushButton("Buscar")
        self.btn_search.setFixedWidth(70)
        self.btn_search.clicked.connect(self._do_discover)
        conn_layout.addWidget(self.btn_search)

        conn_layout.addWidget(QLabel("Puerto:"))
        self.port_s_input = QLineEdit(str(protocol.DEFAULT_PORT))
        self.port_s_input.setFixedWidth(60)
        conn_layout.addWidget(self.port_s_input)

        conn_layout.addWidget(QLabel("PIN:"))
        self.pin_s_input = QLineEdit()
        self.pin_s_input.setFixedWidth(80)
        conn_layout.addWidget(self.pin_s_input)
        conn_layout.addStretch()
        layout.addLayout(conn_layout)

        # 2. Carpetas
        layout.addWidget(QLabel("Carpetas a copiar:"))
        self.folder_vars = {}
        folders_layout = QHBoxLayout()
        for name in FOLDERS:
            path = resolve_folder(name)
            estado = "OK" if path.is_dir() else "NO EXISTE"
            cb = QCheckBox(f"{FOLDER_LABELS.get(name, name)} [{estado}]")
            cb.setChecked(True)
            self.folder_vars[name] = cb
            folders_layout.addWidget(cb)
        layout.addLayout(folders_layout)

        # 3. Controles
        ctrl_layout = QHBoxLayout()
        self.btn_send = QPushButton("▶ Iniciar envío")
        self.btn_send.setFixedHeight(40)
        self.btn_send.clicked.connect(self._start_send)
        
        self.btn_send_stop = QPushButton("■ Detener")
        self.btn_send_stop.setFixedHeight(40)
        self.btn_send_stop.setStyleSheet("background-color: #f38ba8; color: #11111b;")
        self.btn_send_stop.setEnabled(False)
        self.btn_send_stop.clicked.connect(self._stop_send)
        
        ctrl_layout.addWidget(self.btn_send, stretch=2)
        ctrl_layout.addWidget(self.btn_send_stop, stretch=1)
        layout.addLayout(ctrl_layout)

        # 4. Progreso y Estado
        self.prog_s = QProgressBar()
        self.prog_s.setValue(0)
        layout.addWidget(self.prog_s)
        
        self.status_s = QLabel("Listo")
        self.status_s.setStyleSheet("color: gray;")
        layout.addWidget(self.status_s)

        # 5. Log
        self.send_log = QTextEdit()
        self.send_log.setReadOnly(True)
        layout.addWidget(self.send_log)

        return widget

    def _build_recv_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 1. Info de IP
        ips = ", ".join(local_ips())
        lbl_ip = QLabel(f"IP: {ips}")
        lbl_ip.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(lbl_ip)

        # 2. Configuración
        cfg_layout = QHBoxLayout()
        cfg_layout.addWidget(QLabel("Puerto:"))
        self.port_r_input = QLineEdit(str(protocol.DEFAULT_PORT))
        self.port_r_input.setFixedWidth(60)
        cfg_layout.addWidget(self.port_r_input)

        cfg_layout.addWidget(QLabel("PIN:"))
        self.pin_r_input = QLineEdit(str(random.randint(100000, 999999)))
        self.pin_r_input.setFixedWidth(100)
        cfg_layout.addWidget(self.pin_r_input)

        self.btn_new_pin = QPushButton("↻")
        self.btn_new_pin.setFixedSize(30, 30)
        self.btn_new_pin.clicked.connect(self._new_pin)
        cfg_layout.addWidget(self.btn_new_pin)
        cfg_layout.addStretch()
        layout.addLayout(cfg_layout)

        # 3. Destino
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Guardar en:"))
        self.dest_input = QLineEdit(str(Path.home()))
        dest_layout.addWidget(self.dest_input)
        
        btn_pick_dest = QPushButton("...")
        btn_pick_dest.setFixedWidth(40)
        btn_pick_dest.clicked.connect(self._pick_dest)
        dest_layout.addWidget(btn_pick_dest)
        layout.addLayout(dest_layout)

        # 4. Controles
        ctrl_layout = QHBoxLayout()
        self.btn_recv = QPushButton("▶ Iniciar recepción")
        self.btn_recv.setFixedHeight(40)
        self.btn_recv.clicked.connect(self._start_recv)
        
        self.btn_recv_stop = QPushButton("■ Detener")
        self.btn_recv_stop.setFixedHeight(40)
        self.btn_recv_stop.setStyleSheet("background-color: #f38ba8; color: #11111b;")
        self.btn_recv_stop.setEnabled(False)
        self.btn_recv_stop.clicked.connect(self._stop_recv)
        
        ctrl_layout.addWidget(self.btn_recv, stretch=2)
        ctrl_layout.addWidget(self.btn_recv_stop, stretch=1)
        layout.addLayout(ctrl_layout)

        # 5. Estado
        self.status_r = QLabel("Detenido")
        self.status_r.setStyleSheet("color: gray;")
        layout.addWidget(self.status_r)

        # 6. Log
        self.recv_log = QTextEdit()
        self.recv_log.setReadOnly(True)
        layout.addWidget(self.recv_log)

        return widget

    def _switch_tab(self, index):
        self.btn_tab_send.setChecked(index == 0)
        self.btn_tab_recv.setChecked(index == 1)
        self.stack.setCurrentIndex(index)

    def _animate_entrance(self):
        self.anim = QPropertyAnimation(self.glass, b"pos")
        self.anim.setDuration(1200)
        self.anim.setStartValue(QPoint(20, -750))
        self.anim.setEndValue(QPoint(20, 20))
        self.anim.setEasingCurve(QEasingCurve.Type.OutElastic)
        self.anim.start()

    # ---------- Helpers ----------
    def _new_pin(self):
        self.pin_r_input.setText(str(random.randint(100000, 999999)))

    def _pick_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino", self.dest_input.text())
        if d:
            self.dest_input.setText(d)

    def _write_log(self, text_widget, msg):
        text_widget.append(msg)
        # Auto-scroll
        scrollbar = text_widget.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _poll(self):
        """Reemplaza el root.after(120, self._poll) de Tkinter"""
        if self._closing: return
        
        try:
            while True:
                self._write_log(self.send_log, self.send_q.get_nowait())
        except queue.Empty: pass
        try:
            while True:
                self._write_log(self.recv_log, self.recv_q.get_nowait())
        except queue.Empty: pass

        s = self.state["send"]
        self.prog_s.setValue(int(s["pct"]))
        self.status_s.setText(s["text"])
        self.status_r.setText(self.state["recv"]["text"])

        QTimer.singleShot(120, self._poll)

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
            # Actualizar UI desde el hilo usando QTimer
            QTimer.singleShot(0, lambda: self._set_discovered_host(first, found))
        threading.Thread(target=worker, daemon=True).start()

    def _set_discovered_host(self, first, found):
        self.host_input.setText(first)
        self.port_s_input.setText(str(found[first].get("port", protocol.DEFAULT_PORT)))

    def _start_send(self):
        if self.client is not None or SendClient is None:
            if SendClient is None: self.send_q.put("[ERROR] SendClient no importado.")
            return
            
        host = self.host_input.text().strip()
        pin = self.pin_s_input.text().strip()
        if not host or not pin:
            QMessageBox.warning(self, "WCP", "Completa IP y PIN")
            return
            
        folders = [f for f, cb in self.folder_vars.items() if cb.isChecked()]
        if not folders:
            QMessageBox.warning(self, "WCP", "Selecciona al menos una carpeta")
            return
            
        try: port = int(self.port_s_input.text())
        except ValueError: return

        self.btn_send.setEnabled(False)
        self.btn_send_stop.setEnabled(True)
        self.state["send"] = {"pct": 0, "text": "Conectando..."}

        def log(m):
            self.send_q.put(m)
            if m.startswith("[~]"):
                self.state["send"]["text"] = m[4:]
                
        def prog(done, total, db, tb, rate):
            self.state["send"]["pct"] = 100.0 * db / max(tb, 1)
            self.state["send"]["text"] = f"{done}/{total} archivos · {_human(db)}/{_human(tb)} · {_human(int(rate))}/s"

        self.client = SendClient(host, port, pin, folders, log, prog)
        def runner():
            try: self.client.run()
            finally: QTimer.singleShot(0, self._send_done)
        threading.Thread(target=runner, daemon=True).start()

    def _send_done(self):
        ok = self.client.ok if hasattr(self.client, 'ok') else False
        self.client = None
        self.btn_send.setEnabled(True)
        self.btn_send_stop.setEnabled(False)
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
        if self.server is not None or ReceiveServer is None: return
        pin = self.pin_r_input.text().strip()
        dest = self.dest_input.text().strip()
        try: port = int(self.port_r_input.text())
        except ValueError: return

        def log(m): self.recv_q.put(m)
        def prog(ok, skip, b, rate):
            self.state["recv"]["text"] = f"Recibidos: {ok} · Saltados: {skip} · {_human(b)} · {_human(int(rate))}/s"

        self.server = ReceiveServer(port, pin, dest, log, prog)
        self.server.start()
        self.btn_recv.setEnabled(False)
        self.btn_recv_stop.setEnabled(True)
        self.state["recv"]["text"] = "Escuchando..."

    def _stop_recv(self):
        if self.server:
            self.server.stop()
            self.server = None
        self.btn_recv.setEnabled(True)
        self.btn_recv_stop.setEnabled(False)
        self.state["recv"]["text"] = "Detenido"

    # ---------- Arrastrar ventana ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_bar.geometry().contains(event.position().toPoint()):
                self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def _on_close(self):
        self._closing = True
        if self.server: self.server.stop()
        if self.client: self.client.stop()
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = WCPWindow()
    window.show()
    sys.exit(app.exec())
