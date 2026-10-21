"""Preferencias de WCP en JSON (~/.wcp_config.json)."""
import json
from pathlib import Path

from . import protocol
from .scanner import FOLDERS, resolve_folder

CONFIG_FILE = Path.home() / ".wcp_config.json"


def defaults():
    return {
        "language": "es",         # "es" | "en"
        "theme": "dark_warm",     # clave de gui.TEMAS
        "confirm_receive": True,  # pedir permiso antes de aceptar un envío entrante
        "default_port": protocol.DEFAULT_PORT,
        "last_ip": "",
        # carpeta donde el receptor guarda lo que llega de cada carpeta del origen
        "dest_paths": {name: str(resolve_folder(name)) for name in FOLDERS},
    }


class ConfigEngine:
    def __init__(self, path=CONFIG_FILE):
        self.path = Path(path)
        self.config = defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            dest = data.pop("dest_paths", {})
            self.config.update(data)
            self.config["dest_paths"].update(
                {k: v for k, v in dest.items() if k in FOLDERS and v})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as e:
            print(f"[config] No se pudo leer {self.path}: {e}")

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self.config, indent=4, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            print(f"[config] No se pudo guardar {self.path}: {e}")

    def set(self, key, value):
        self.config[key] = value
        self.save()


config = ConfigEngine()
