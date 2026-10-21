from wcp.config_engine import ConfigEngine
from wcp.scanner import FOLDERS


def test_defaults_cover_all_folders(tmp_path):
    c = ConfigEngine(tmp_path / "c.json")
    assert set(c.config["dest_paths"]) == set(FOLDERS) >= {"Desktop", "Downloads", "Documents", "Music", "Pictures"}


def test_roundtrip_and_partial_file(tmp_path):
    p = tmp_path / "c.json"
    c = ConfigEngine(p)
    c.config["dest_paths"]["Music"] = "X:/musica"
    c.set("default_port", 9000)
    c2 = ConfigEngine(p)
    assert c2.config["default_port"] == 9000 and c2.config["dest_paths"]["Music"] == "X:/musica"
    p.write_text('{"dest_paths": {"Desktop": "D"}}', encoding="utf-8")  # faltan claves -> defaults
    c3 = ConfigEngine(p)
    assert c3.config["dest_paths"]["Desktop"] == "D" and c3.config["dest_paths"]["Music"]


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{no es json", encoding="utf-8")
    assert ConfigEngine(p).config["default_port"]


def test_every_theme_defines_the_same_colors():
    from wcp.gui import TEMAS
    claves = set(TEMAS["dark_warm"][2])
    assert all(set(t[2]) == claves for t in TEMAS.values())
    assert {"dark_blue", "black", "light"} <= set(TEMAS)
