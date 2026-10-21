"""Interfaz CustomTkinter para WCP."""
import json
import queue
import secrets
import socket
import threading
import time
from pathlib import Path
from tkinter import Toplevel, filedialog, messagebox

import customtkinter as ctk

from . import APP_NAME, __version__, protocol
from .client import SendClient
from .config_engine import config, defaults
from .i18n import IDIOMAS, _, lang, set_lang
from .scanner import FOLDERS, resolve_folder
from .server import ReceiveServer

FOLDER_LABELS = {
    "Desktop": "Escritorio",
    "Documents": "Documentos",
    "Downloads": "Descargas",
    "Music": "Música",
    "Pictures": "Fotos",
}


# ═══════════════════════════════════════════════════════════════
#  TEMAS
# ═══════════════════════════════════════════════════════════════
class P:
    """Paleta activa; aplicar_tema() sobrescribe estos valores antes de construir la UI."""
    R_CARD, R_INPUT, R_BTN = 12, 8, 8


def _tema(bg, topbar, card, card_alt, border, txt, txt_2, txt_3, accent, accent_hover, txt_inv,
          success="#10B981"):
    return dict(BG=bg, TOPBAR=topbar, CARD=card, CARD_ALT=card_alt, BORDER=border, TXT=txt,
                TXT_2=txt_2, TXT_3=txt_3, ACCENT=accent, ACCENT_HOVER=accent_hover,
                TXT_INV=txt_inv, SUCCESS=success, DANGER="#EF4444")


# clave: (nombre en español, nombre en inglés, colores)
TEMAS = {
    "dark_warm": ("Oscuro cálido", "Warm dark", _tema(
        "#0F0F11", "#16161A", "#1C1C21", "#26262D", "#2D2D35",
        "#F3F4F6", "#A1A1AA", "#71717A", "#F59E0B", "#D97706", "#111827")),
    "dark_blue": ("Azul", "Blue", _tema(
        "#0B1220", "#0F1A2E", "#13223B", "#1B2F52", "#25406B",
        "#E6EEF9", "#9DB2D1", "#6B83A8", "#3B82F6", "#2563EB", "#FFFFFF")),
    "black": ("Negro", "Black", _tema(
        "#000000", "#0A0A0A", "#111111", "#1A1A1A", "#262626",
        "#FFFFFF", "#A3A3A3", "#737373", "#FFFFFF", "#D4D4D4", "#000000")),
    "light": ("Blanco", "White", _tema(
        "#F4F5F7", "#FFFFFF", "#FFFFFF", "#EEF0F3", "#D8DCE3",
        "#111827", "#4B5563", "#9CA3AF", "#2563EB", "#1D4ED8", "#FFFFFF", success="#047857")),
    "green": ("Verde", "Green", _tema(
        "#0C1410", "#101C16", "#14241C", "#1C3327", "#27503A",
        "#E8F5EE", "#9BC2AC", "#6B9680", "#10B981", "#059669", "#04130C")),
    "purple": ("Morado", "Purple", _tema(
        "#110D1A", "#171123", "#1D1630", "#2A2145", "#3B2E63",
        "#F1ECFA", "#B3A6D1", "#8374AB", "#8B5CF6", "#7C3AED", "#FFFFFF")),
}

def aplicar_preferencias():
    """Aplica idioma y tema guardados en la configuración."""
    set_lang(config.config["language"])
    clave = config.config["theme"] if config.config["theme"] in TEMAS else "dark_warm"
    for k, v in TEMAS[clave][2].items():
        setattr(P, k, v)
    ctk.set_appearance_mode("light" if clave == "light" else "dark")


def _nombre_carpeta(name):
    return _(FOLDER_LABELS.get(name, name))


def F(size=12, weight="normal"): return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)
def FM(size=11, weight="normal"): return ctk.CTkFont(family="Consolas", size=size, weight=weight)


# ═══════════════════════════════════════════════════════════════
#  COMPONENTES
# ═══════════════════════════════════════════════════════════════
class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=P.CARD, border_width=1, border_color=P.BORDER,
                         corner_radius=P.R_CARD, **kw)


class TopNavButton(ctk.CTkButton):
    def __init__(self, master, texto, comando, is_active=False):
        super().__init__(master, text=texto, command=comando, fg_color="transparent",
                         hover_color=P.CARD_ALT, text_color=P.TXT_2, font=F(13, "bold"),
                         corner_radius=6, height=36)
        self.set_active(is_active)

    def set_active(self, is_active):
        if is_active:
            self.configure(text_color=P.ACCENT, fg_color=P.CARD_ALT)
        else:
            self.configure(text_color=P.TXT_2, fg_color="transparent")


class Btn(ctk.CTkButton):
    def __init__(self, master, texto, comando=None, icono="", tipo="primary", ancho=120, height=38):
        colores = {"primary": (P.ACCENT, P.ACCENT_HOVER, P.TXT_INV),
                   "secondary": (P.CARD, P.CARD_ALT, P.TXT)}
        fg, hov, txt = colores.get(tipo, colores["primary"])
        super().__init__(master, text=f"{icono}  {texto}".strip(), command=comando, width=ancho,
                         height=height, corner_radius=P.R_BTN, fg_color=fg, hover_color=hov,
                         text_color=txt, text_color_disabled=P.TXT_3,
                         border_width=1 if tipo == "secondary" else 0,
                         border_color=P.BORDER if tipo == "secondary" else fg,
                         font=F(12, "bold"))


class InputField(ctk.CTkFrame):
    def __init__(self, master, etiqueta, placeholder="", value=""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=etiqueta, font=F(11, "bold"), text_color=P.TXT,
                     anchor="w").pack(anchor="w", pady=(0, 4))
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x")
        self._fila = fila
        self.entry = ctk.CTkEntry(fila, placeholder_text=placeholder, height=40,
                                  corner_radius=P.R_INPUT, border_width=1, border_color=P.BORDER,
                                  fg_color=P.CARD_ALT, text_color=P.TXT,
                                  placeholder_text_color=P.TXT_3, font=F(13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.boton = None
        self.set(value)

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, "end")
        self.entry.insert(0, str(value))

    def add_button(self, texto, comando, ancho=70):
        self.boton = Btn(self._fila, texto, comando, tipo="secondary", ancho=ancho, height=40)
        self.boton.pack(side="left", padx=(8, 0))
        return self

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        if self.boton:
            self.boton.configure(state=state)


class SectionTitle(ctk.CTkFrame):
    def __init__(self, master, titulo, descripcion=""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=titulo, font=F(15, "bold"), text_color=P.TXT,
                     anchor="w").pack(anchor="w")
        if descripcion:
            ctk.CTkLabel(self, text=descripcion, font=F(12), text_color=P.TXT_2,
                         anchor="w").pack(anchor="w", pady=(2, 0))


def Menu(master, values, variable):
    return ctk.CTkOptionMenu(master, values=values, variable=variable, fg_color=P.CARD_ALT,
                             button_color=P.ACCENT, button_hover_color=P.ACCENT_HOVER,
                             text_color=P.TXT, font=F(12), dropdown_fg_color=P.CARD,
                             dropdown_text_color=P.TXT, dropdown_hover_color=P.CARD_ALT)


def Switch(master, texto, variable, comando=None):
    return ctk.CTkSwitch(master, text=texto, variable=variable, command=comando,
                         progress_color=P.ACCENT, button_color=P.TXT, button_hover_color=P.TXT_2,
                         fg_color=P.CARD_ALT, text_color=P.TXT, font=F(12))


def Log(master, height=200):
    box = ctk.CTkTextbox(master, height=height, state="disabled", fg_color=P.BG,
                         text_color=P.SUCCESS, font=FM(11), wrap="word",
                         border_width=1, border_color=P.BORDER)
    box.tag_config("err", foreground=P.DANGER)
    box.tag_config("warn", foreground=P.ACCENT)
    box.tag_config("info", foreground=P.TXT_2)
    return box


def _tag_linea(msg):
    if msg.startswith(("[!]", "[ERROR]")):
        return "err"
    if msg.startswith("[~]"):
        return "warn"
    if msg.startswith(("[i]", "[.]", "[+]")):
        return "info"
    return None


def Progress(master):
    bar = ctk.CTkProgressBar(master, height=10, fg_color=P.CARD_ALT, progress_color=P.ACCENT)
    bar.set(0)
    return bar


def Check(master, texto, variable):
    return ctk.CTkCheckBox(master, text=texto, variable=variable, fg_color=P.ACCENT,
                           hover_color=P.ACCENT_HOVER, border_color=P.BORDER,
                           checkmark_color=P.TXT_INV, text_color=P.TXT, font=F(12))


# ═══════════════════════════════════════════════════════════════
#  RED
# ═══════════════════════════════════════════════════════════════
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
            obj = json.loads(data.decode("utf-8"))
            if obj.get("service") == "wcp":
                found[addr[0]] = obj
        except socket.timeout:
            continue
        except Exception:
            continue
    s.close()
    return found


def _eta(restante, rate):
    if rate < 1 or restante <= 0:
        return "ETA --"
    m, sec = divmod(int(restante / rate), 60)
    h, m = divmod(m, 60)
    return "ETA " + (f"{h}h {m:02d}m" if h else f"{m}m {sec:02d}s" if m else f"{sec}s")


def _human(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ═══════════════════════════════════════════════════════════════
#  APLICACIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════
class App:
    def __init__(self, root):
        self.root = root
        aplicar_preferencias()
        root.title(APP_NAME)
        root.geometry("1100x750")
        root.minsize(950, 650)
        root.configure(fg_color=P.BG)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self.send_q = queue.Queue()
        self.recv_q = queue.Queue()
        # texto = plantilla en español (se traduce al mostrarla) + valores; así sobrevive a un cambio de idioma
        self.state = {
            "send": {"pct": 0, "tpl": "Listo", "kw": {}},
            "recv": {"pct": 0, "tpl": "Detenido", "kw": {}},
        }
        self.send_lines = []
        self.recv_lines = []
        self.server = None
        self.client = None
        self._closing = False
        self._vistas = {}
        self._nav_buttons = {}
        self._save_after = None

        self._build_topbar()
        self._build_content()
        self._show_view("enviar")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # ---------- Estructura ----------
    def _build_topbar(self):
        top = ctk.CTkFrame(self.root, height=64, corner_radius=0, fg_color=P.TOPBAR,
                           border_width=1, border_color=P.BORDER)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(top, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="w", padx=20, pady=12)
        icon_box = ctk.CTkFrame(logo, width=32, height=32, corner_radius=8, fg_color=P.ACCENT)
        icon_box.pack(side="left")
        icon_box.pack_propagate(False)
        ctk.CTkLabel(icon_box, text="W", font=F(16, "bold"), text_color=P.TXT_INV).pack(expand=True)
        ctk.CTkLabel(logo, text="WCP", font=F(18, "bold"), text_color=P.TXT).pack(side="left", padx=(10, 0))

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.grid(row=0, column=1, sticky="w", padx=40)
        for clave, texto in (("enviar", _("▲  Enviar Archivos")), ("recibir", _("▼  Recibir Archivos"))):
            b = TopNavButton(nav, texto, lambda c=clave: self._show_view(c))
            b.pack(side="left", padx=5)
            self._nav_buttons[clave] = b

        acc = ctk.CTkFrame(top, fg_color="transparent")
        acc.grid(row=0, column=2, sticky="e", padx=20)
        self._nav_buttons["config"] = TopNavButton(acc, _("⚙️  Ajustes"), lambda: self._show_view("config"))
        self._nav_buttons["config"].pack(side="left")

    def _build_content(self):
        wrap = ctk.CTkFrame(self.root, corner_radius=0, fg_color=P.BG)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        self.content = wrap

        self._vistas["enviar"] = self._view_enviar()
        self._vistas["recibir"] = self._view_recibir()
        self._vistas["config"] = self._view_config()

    def _show_view(self, clave):
        for v in self._vistas.values():
            v.grid_forget()
        self._vistas[clave].grid(row=0, column=0, sticky="nsew")
        for c, btn in self._nav_buttons.items():
            btn.set_active(c == clave)

    def _nueva_vista(self, titulo, subtitulo=""):
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent", corner_radius=0)
        interior = ctk.CTkFrame(scroll, fg_color="transparent")
        interior.pack(fill="both", expand=True, padx=40, pady=32)
        ctk.CTkLabel(interior, text=titulo, font=F(26, "bold"), text_color=P.TXT,
                     anchor="w").pack(anchor="w")
        if subtitulo:
            ctk.CTkLabel(interior, text=subtitulo, font=F(13), text_color=P.TXT_2,
                         anchor="w").pack(anchor="w", pady=(4, 0))
        return scroll, interior

    # ---------- ENVIAR ----------
    def _view_enviar(self):
        scroll, box = self._nueva_vista(_("Enviar Archivos"))

        card = Card(box)
        card.pack(fill="x", pady=(20, 16))
        SectionTitle(card, _("Destino")).pack(anchor="w", padx=24, pady=(24, 16))
        self.host_s = InputField(card, _("Dirección IP / host"), "192.168.0.245",
                                 value=config.config["last_ip"])
        self.host_s.add_button(_("Buscar"), self._do_discover)
        self.host_s.pack(fill="x", padx=24, pady=(0, 16))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 24))
        self.port_s = InputField(row, _("Puerto"), str(protocol.DEFAULT_PORT),
                                 value=config.config["default_port"])
        self.port_s.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.pin_s = InputField(row, "PIN", "XXXXXX")
        self.pin_s.pack(side="left", fill="x", expand=True)

        card = Card(box)
        card.pack(fill="x", pady=(0, 16))
        SectionTitle(card, _("Carpetas")).pack(anchor="w", padx=24, pady=(24, 12))
        self.folder_vars = {}
        for i, name in enumerate(FOLDERS):
            var = ctk.BooleanVar(value=True)
            self.folder_vars[name] = var
            path = resolve_folder(name)
            estado = "OK" if path.is_dir() else _("NO EXISTE")
            Check(card, f"{_nombre_carpeta(name)}   ·   {path}   [{estado}]", var).pack(
                anchor="w", padx=24, pady=(0, 24 if i == len(FOLDERS) - 1 else 10))

        bar = ctk.CTkFrame(box, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 12))
        self.btn_send = Btn(bar, _("Iniciar envío"), self._start_send, icono="▶", height=45, ancho=170)
        self.btn_send.pack(side="left")
        self.btn_send_stop = Btn(bar, _("Detener"), self._stop_send, icono="■", tipo="secondary",
                                 height=45, ancho=120)
        self.btn_send_stop.configure(state="disabled")
        self.btn_send_stop.pack(side="left", padx=10)

        self.prog_s = Progress(box)
        self.prog_s.pack(fill="x", pady=(4, 6))
        self.status_s = ctk.CTkLabel(box, text=_("Listo"), font=F(12), text_color=P.TXT_2, anchor="w")
        self.status_s.pack(anchor="w", pady=(0, 12))
        self.send_log = Log(box)
        self.send_log.pack(fill="x")
        return scroll

    # ---------- RECIBIR ----------
    def _view_recibir(self):
        scroll, box = self._nueva_vista(_("Recibir Archivos"))

        card = Card(box)
        card.pack(fill="x", pady=(20, 16))
        SectionTitle(card, _("Tu PC"), _("Comparte estos datos con el origen.")).pack(
            anchor="w", padx=24, pady=(24, 12))
        ips = local_ips()
        fila_ip = ctk.CTkFrame(card, fg_color="transparent")
        fila_ip.pack(anchor="w", padx=24, pady=(0, 12))
        ctk.CTkLabel(fila_ip, text=f"IP: {', '.join(ips)}", font=F(14, "bold"),
                     text_color=P.ACCENT).pack(side="left")
        Btn(fila_ip, "⧉", lambda: self._copiar(ips[0]), tipo="secondary", ancho=44,
            height=30).pack(side="left", padx=(10, 0))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 24))
        self.port_r = InputField(row, _("Puerto"), str(protocol.DEFAULT_PORT),
                                 value=config.config["default_port"])
        self.port_r.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.pin_r = InputField(row, "PIN", value=f"{100000 + secrets.randbelow(900000)}")
        self.pin_r.add_button("↻", self._new_pin, ancho=44)
        self.pin_r.add_button("⧉", lambda: self._copiar(self.pin_r.get()), ancho=44)
        self.pin_r.pack(side="left", fill="x", expand=True)

        card = Card(box)
        card.pack(fill="x", pady=(0, 16))
        SectionTitle(card, _("Carpeta destino")).pack(anchor="w", padx=24, pady=(24, 12))
        self.usar_defecto = ctk.BooleanVar(value=True)
        Switch(card, _("Usar las carpetas de destino por defecto (Ajustes)"),
               self.usar_defecto, self._toggle_destino).pack(anchor="w", padx=24, pady=(0, 12))
        self.dest_r = InputField(card, _("Una sola carpeta para todo"), "C:\\Users\\...",
                                 value=str(Path.home()))
        self.dest_r.add_button("...", lambda: self._pick(self.dest_r))
        self.dest_r.pack(fill="x", padx=24, pady=(0, 24))
        self._toggle_destino()

        bar = ctk.CTkFrame(box, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 12))
        self.btn_recv = Btn(bar, _("Iniciar recepción"), self._start_recv, icono="▶", height=45, ancho=190)
        self.btn_recv.pack(side="left")
        self.btn_recv_stop = Btn(bar, _("Detener"), self._stop_recv, icono="■", tipo="secondary",
                                 height=45, ancho=120)
        self.btn_recv_stop.configure(state="disabled")
        self.btn_recv_stop.pack(side="left", padx=10)

        self.prog_r = Progress(box)
        self.prog_r.pack(fill="x", pady=(4, 6))
        self.status_r = ctk.CTkLabel(box, text=_("Detenido"), font=F(12), text_color=P.TXT_2, anchor="w")
        self.status_r.pack(anchor="w", pady=(0, 12))
        self.recv_log = Log(box)
        self.recv_log.pack(fill="x")
        return scroll

    # ---------- AJUSTES ----------
    def _view_config(self):
        scroll, box = self._nueva_vista(_("Ajustes"), _("Configuración general de WCP."))

        card = Card(box)
        card.pack(fill="x", pady=(24, 16))
        SectionTitle(card, _("Apariencia e idioma")).pack(anchor="w", padx=24, pady=(24, 16))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 24))
        ctk.CTkLabel(row, text=_("Idioma:"), font=F(12), text_color=P.TXT).pack(side="left")
        self.lang_var = ctk.StringVar(value=IDIOMAS[lang()])
        Menu(row, list(IDIOMAS.values()), self.lang_var).pack(side="left", padx=(10, 40))
        ctk.CTkLabel(row, text=_("Color de interfaz:"), font=F(12), text_color=P.TXT).pack(side="left")
        self.temas_nombre = {k: v[1 if lang() == "en" else 0] for k, v in TEMAS.items()}
        self.theme_var = ctk.StringVar(value=self.temas_nombre.get(config.config["theme"], self.temas_nombre["dark_warm"]))
        Menu(row, list(self.temas_nombre.values()), self.theme_var).pack(side="left", padx=10)

        card = Card(box)
        card.pack(fill="x", pady=(0, 16))
        SectionTitle(card, _("Red")).pack(anchor="w", padx=24, pady=(24, 16))
        self.port_cfg = InputField(card, _("Puerto por defecto"), str(protocol.DEFAULT_PORT),
                                   value=config.config["default_port"])
        self.port_cfg.pack(fill="x", padx=24, pady=(0, 16))
        self.confirm_var = ctk.BooleanVar(value=config.config["confirm_receive"])
        Switch(card, _("Pedir confirmación antes de recibir"), self.confirm_var).pack(
            anchor="w", padx=24, pady=(0, 24))

        card = Card(box)
        card.pack(fill="x", pady=(0, 16))
        SectionTitle(card, _("Carpetas de destino por defecto"),
                     _("Dónde guarda este PC lo que recibe de cada carpeta del origen. "
                       "Se aplican al iniciar la recepción.")).pack(anchor="w", padx=24, pady=(24, 16))
        self.dest_cfg = {}
        for i, name in enumerate(FOLDERS):
            f = InputField(card, _nombre_carpeta(name), value=config.config["dest_paths"][name])
            f.add_button("...", lambda f=f: self._pick(f))
            f.pack(fill="x", padx=24, pady=(0, 24 if i == len(FOLDERS) - 1 else 14))
            self.dest_cfg[name] = f

        card = Card(box)
        card.pack(fill="x")
        SectionTitle(card, _("Acerca de WCP")).pack(anchor="w", padx=24, pady=(24, 16))
        info = (f"{_('Versión')}: {__version__}\n"
                f"{_('Motor de transferencia: TCP con reanudación de archivos.')}\n"
                f"{_('Desarrollado con Python y CustomTkinter.')}")
        ctk.CTkLabel(card, text=info, font=F(12), text_color=P.TXT_2, justify="left").pack(
            anchor="w", padx=24, pady=(0, 16))
        ctk.CTkLabel(card, text=_("Licencias"), font=F(13, "bold"), text_color=P.TXT).pack(
            anchor="w", padx=24, pady=(0, 4))
        lic = (f"• MIT License\n• Apache License 2.0\n"
               f"{_('WCP se distribuye bajo cualquiera de las dos, a tu elección.')}")
        ctk.CTkLabel(card, text=lic, font=F(12), text_color=P.TXT_2, justify="left").pack(
            anchor="w", padx=24, pady=(0, 24))

        card = Card(box)
        card.pack(fill="x", pady=(16, 0))
        SectionTitle(card, _("Cuenta KODECOUNT"),
                     _("Próximamente: vincula tu cuenta de KODECOUNT con WCP.")).pack(
            anchor="w", padx=24, pady=(24, 16))
        btn = Btn(card, _("Vincular cuenta"), icono="🔗", tipo="secondary", ancho=170)
        btn.configure(state="disabled")
        btn.pack(anchor="w", padx=24, pady=(0, 24))

        self.btn_save = Btn(box, _("Guardar Cambios"), self._save_config, icono="💾", height=45, ancho=190)
        self.btn_save.pack(anchor="e", pady=20)
        return scroll

    def _save_config(self):
        try:
            port = int(self.port_cfg.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("WCP", _("Puerto inválido"))
            return
        base = defaults()["dest_paths"]
        paths = {}
        for name, field in self.dest_cfg.items():
            paths[name] = field.get() or base[name]  # vacío = volver al valor del sistema
            field.set(paths[name])
        idioma = next(k for k, v in IDIOMAS.items() if v == self.lang_var.get())
        tema = next(k for k, v in self.temas_nombre.items() if v == self.theme_var.get())
        cambio = (idioma, tema) != (config.config["language"], config.config["theme"])
        config.config.update(default_port=port, dest_paths=paths, language=idioma, theme=tema,
                             confirm_receive=self.confirm_var.get())
        config.save()
        self.port_s.set(port)
        if self.server is None:
            self.port_r.set(port)
        if cambio:
            # diferido: este botón se destruye en la reconstrucción
            self.root.after(50, lambda: self._reconstruir("config"))
            return
        self.btn_save.configure(text=_("✓  Guardado"), fg_color=P.SUCCESS)
        self._save_after = self.root.after(2000, lambda: self.btn_save.configure(
            text="💾  " + _("Guardar Cambios"), fg_color=P.ACCENT))

    def _reconstruir(self, vista):
        """Reaplica idioma y tema reconstruyendo la UI; conserva campos, registros y envío/recepción en curso."""
        if self._save_after:
            self.root.after_cancel(self._save_after)
            self._save_after = None
        snap = dict(
            host=self.host_s.get(), port_s=self.port_s.get(), pin_s=self.pin_s.get(),
            folders={n: v.get() for n, v in self.folder_vars.items()},
            port_r=self.port_r.get(), pin_r=self.pin_r.get(), dest=self.dest_r.get(),
            usar=self.usar_defecto.get())
        aplicar_preferencias()
        for w in self.root.winfo_children():
            if not isinstance(w, Toplevel):  # un diálogo abierto debe seguir esperando respuesta
                w.destroy()
        self._vistas.clear()
        self._nav_buttons.clear()
        self.root.configure(fg_color=P.BG)
        self._build_topbar()
        self._build_content()

        self.host_s.set(snap["host"])
        self.port_s.set(snap["port_s"])
        self.pin_s.set(snap["pin_s"])
        for n, v in snap["folders"].items():
            self.folder_vars[n].set(v)
        self.port_r.set(snap["port_r"])
        self.pin_r.set(snap["pin_r"])
        self.dest_r.set_enabled(True)  # un campo desactivado no admite escritura
        self.dest_r.set(snap["dest"])
        self.usar_defecto.set(snap["usar"])
        self._toggle_destino()
        for box, lines in ((self.send_log, self.send_lines), (self.recv_log, self.recv_lines)):
            box.configure(state="normal")
            for line in lines:
                box.insert("end", line + "\n", _tag_linea(line))
            box.see("end")
            box.configure(state="disabled")
        if self.client:
            self.btn_send.configure(state="disabled")
            self.btn_send_stop.configure(state="normal")
        if self.server:
            self.btn_recv.configure(state="disabled")
            self.btn_recv_stop.configure(state="normal")
        self._show_view(vista)

    # ---------- Helpers UI ----------
    def _copiar(self, texto):
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)

    def _new_pin(self):
        self.pin_r.set(f"{100000 + secrets.randbelow(900000)}")

    def _toggle_destino(self):
        self.dest_r.set_enabled(not self.usar_defecto.get())

    def _pick(self, field):
        p = filedialog.askdirectory(initialdir=field.get() or str(Path.home()))
        if p:
            field.set(p)

    def _write_log(self, box, lines, msg):
        lines.append(msg)
        box.configure(state="normal")
        box.insert("end", msg + "\n", _tag_linea(msg))
        box.see("end")
        box.configure(state="disabled")

    @staticmethod
    def _texto(estado):
        t = _(estado["tpl"])
        return t.format(**estado["kw"]) if estado["kw"] else t

    def _set_estado(self, cual, tpl, pct=None, **kw):
        e = self.state[cual]
        e["tpl"], e["kw"] = tpl, kw
        if pct is not None:
            e["pct"] = pct

    def _poll(self):
        if self._closing:
            return
        try:
            while True:
                self._write_log(self.send_log, self.send_lines, self.send_q.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._write_log(self.recv_log, self.recv_lines, self.recv_q.get_nowait())
        except queue.Empty:
            pass

        for cual, barra, etiqueta in (("send", self.prog_s, self.status_s),
                                      ("recv", self.prog_r, self.status_r)):
            e = self.state[cual]
            barra.set(e["pct"] / 100)
            color = (P.SUCCESS if e["tpl"].startswith("Completado")
                     else P.DANGER if e["tpl"].startswith("Interrumpido") else P.TXT_2)
            etiqueta.configure(text=self._texto(e), text_color=color)

        self.root.after(120, self._poll)

    # ---------- ENVIAR acciones ----------
    def _do_discover(self):
        self.send_q.put(_("[i] Buscando servidores WCP en la red (2s)..."))

        def worker():
            found = discover(2.5)
            if not found:
                self.send_q.put(_("[!] No se encontraron servidores"))
                return
            first = next(iter(found))
            self.send_q.put(_("[OK] Encontrados: {}").format(", ".join(found)))

            def set_host():
                self.host_s.set(first)
                self.port_s.set(found[first].get("port", protocol.DEFAULT_PORT))
            self.root.after(0, set_host)
        threading.Thread(target=worker, daemon=True).start()

    def _start_send(self):
        if self.client is not None:
            return
        host = self.host_s.get()
        pin = self.pin_s.get()
        if not host or not pin:
            messagebox.showwarning("WCP", _("Completa IP y PIN"))
            return
        folders = [f for f, v in self.folder_vars.items() if v.get()]
        if not folders:
            messagebox.showwarning("WCP", _("Selecciona al menos una carpeta"))
            return
        try:
            port = int(self.port_s.get())
        except ValueError:
            messagebox.showerror("WCP", _("Puerto inválido"))
            return

        config.set("last_ip", host)
        self.btn_send.configure(state="disabled")
        self.btn_send_stop.configure(state="normal")
        self._set_estado("send", "Conectando...", pct=0)

        def log(m):
            self.send_q.put(m)
            if m.startswith("[~]"):  # reconexión: visible también en la barra de estado
                self._set_estado("send", m[4:])

        def prog(done, total, db, tb, rate):
            self._set_estado("send", "{done}/{total} archivos · {db}/{tb} · {rate}/s · {eta}",
                             pct=100.0 * db / max(tb, 1), done=done, total=total,
                             db=_human(db), tb=_human(tb), rate=_human(int(rate)),
                             eta=_eta(tb - db, rate))

        self.client = SendClient(host, port, pin, folders, log, prog,
                                 on_conflict=self._ask_conflict)

        def runner():
            try:
                self.client.run()
            finally:
                self.root.after(0, self._send_done)

        threading.Thread(target=runner, daemon=True).start()

    def _dialogo(self, titulo, texto, nombre, botones, casilla=None, defecto=None):
        """Muestra un diálogo desde cualquier hilo y espera.
        botones: [(texto, valor, tipo)]. Devuelve (valor elegido, casilla marcada)."""
        done = threading.Event()
        result = {"valor": defecto, "marca": False}

        def show():
            win = ctk.CTkToplevel(self.root, fg_color=P.CARD)
            win.title(titulo)
            win.transient(self.root)
            win.resizable(False, False)
            ctk.CTkLabel(win, text=texto, font=F(12), text_color=P.TXT_2).pack(
                anchor="w", padx=20, pady=(20, 2))
            ctk.CTkLabel(win, text=nombre, font=F(13, "bold"), text_color=P.TXT, wraplength=420,
                         justify="left").pack(anchor="w", padx=20, pady=(0, 12))
            marca = ctk.BooleanVar(value=False)
            if casilla:
                Check(win, casilla, marca).pack(anchor="w", padx=20)

            def pick(valor):
                result["valor"] = valor
                result["marca"] = marca.get()
                win.destroy()

            bar = ctk.CTkFrame(win, fg_color="transparent")
            bar.pack(fill="x", padx=20, pady=20)
            for t, valor, tipo in botones:
                Btn(bar, t, lambda v=valor: pick(v), tipo=tipo, ancho=110).pack(
                    side="left", padx=(0, 8))
            win.protocol("WM_DELETE_WINDOW", lambda: pick(defecto))
            win.lift()
            win.after(100, win.grab_set)  # CTkToplevel aún no es visible al crearse
            win.bind("<Destroy>", lambda e: done.set() if e.widget is win else None)

        self.root.after(0, show)
        done.wait()
        return result["valor"], result["marca"]

    def _ask_conflict(self, name):
        return self._dialogo(
            _("Archivo existente"), _("El archivo ya existe en el destino y es distinto:"), name,
            [(_("Omitir"), "skip", "secondary"), (_("Sobrescribir"), "overwrite", "primary"),
             (_("Cancelar"), "cancel", "secondary")],
            casilla=_("Aplicar a todos los siguientes"), defecto="cancel")

    def _ask_accept(self, host, ip):
        elegido, _todo = self._dialogo(
            _("Solicitud de envío"), _("Este equipo quiere enviarte archivos:"), f"{host} ({ip})",
            [(_("Aceptar"), True, "primary"), (_("Rechazar"), False, "secondary")], defecto=False)
        return elegido

    def _send_done(self):
        ok = self.client.ok
        self.client = None
        self.btn_send.configure(state="normal")
        self.btn_send_stop.configure(state="disabled")
        if ok:
            self._set_estado("send", "Completado ✔", pct=100)
        else:
            self._set_estado("send", "Interrumpido — pulsa Iniciar para reanudar")

    def _stop_send(self):
        if self.client:
            self.client.stop()
            self.send_q.put(_("[!] Deteniendo..."))

    # ---------- RECIBIR acciones ----------
    def _start_recv(self):
        if self.server is not None:
            return
        pin = self.pin_r.get()
        dest = self.dest_r.get()
        try:
            port = int(self.port_r.get())
        except ValueError:
            messagebox.showerror("WCP", _("Puerto inválido"))
            return
        usar_defecto = self.usar_defecto.get()
        if not usar_defecto and not dest:
            messagebox.showerror("WCP", _("Elige carpeta destino"))
            return

        def log(m): self.recv_q.put(m)

        def prog(ok, skip, b, rate, pct):
            self._set_estado("recv", "Recibidos: {ok} · Saltados: {skip} · {b} · {rate}/s",
                             pct=pct, ok=ok, skip=skip, b=_human(b), rate=_human(int(rate)))

        dest_map = dict(config.config["dest_paths"]) if usar_defecto else None
        on_accept = self._ask_accept if config.config["confirm_receive"] else None
        self.server = ReceiveServer(port, pin, dest or str(Path.home()), log, prog,
                                    dest_map=dest_map, on_accept=on_accept)
        self.server.start()
        self.btn_recv.configure(state="disabled")
        self.btn_recv_stop.configure(state="normal")
        self._set_estado("recv", "Escuchando...", pct=0)

    def _stop_recv(self):
        if self.server:
            self.server.stop()
            self.server = None
        self.btn_recv.configure(state="normal")
        self.btn_recv_stop.configure(state="disabled")
        self._set_estado("recv", "Detenido", pct=0)

    def _on_close(self):
        self._closing = True
        try:
            if self.server:
                self.server.stop()
            if self.client:
                self.client.stop()
        finally:
            self.root.destroy()
