"""Localiza y recorre las carpetas del perfil de usuario."""
import os
import sys
from pathlib import Path

from .i18n import _

FOLDERS = ["Desktop", "Documents", "Downloads", "Music", "Pictures"]


def _win_known_folder(name):
    try:
        import winreg
    except ImportError:
        return None
    mapping = {
        "Desktop": "Desktop",
        "Documents": "Personal",
        "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "Music": "My Music",
        "Pictures": "My Pictures",
    }
    key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            val, _ = winreg.QueryValueEx(k, mapping[name])
            return Path(os.path.expandvars(val))
    except OSError:
        return None


def resolve_folder(name):
    if sys.platform == "win32":
        p = _win_known_folder(name)
        if p and p.is_dir():
            return p
    home = Path.home()
    p = home / name
    if p.is_dir():
        return p
    od = os.environ.get("OneDrive")
    if od:
        p2 = Path(od) / name
        if p2.is_dir():
            return p2
    return home / name


def walk(selected, on_log=None):
    """Genera tuples: (kind, label, root, rel, path, size, mtime)"""
    for label in selected:
        root = resolve_folder(label)
        if not root.is_dir():
            if on_log:
                on_log(_("[!] No existe: {}").format(root))
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            original_dirs = list(dirnames)
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            dp = Path(dirpath)
            if dp != root and not filenames and not original_dirs:
                yield ("dir", label, root, dp.relative_to(root), None, 0, 0)
            for fn in filenames:
                if fn.startswith("."):
                    continue
                p = dp / fn
                try:
                    st = p.stat()
                except OSError:
                    continue
                yield ("file", label, root, p.relative_to(root), p, st.st_size, st.st_mtime)
