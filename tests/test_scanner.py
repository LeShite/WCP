from wcp import scanner


def test_walk_skips_wcp_exe_only(tmp_path, monkeypatch):
    d = tmp_path / "Downloads"
    d.mkdir()
    for n in ("WCP.exe", "WCP (2).exe", "wcp-portable.EXE", "setup.exe", "wcp.txt", "notas.txt"):
        (d / n).write_bytes(b"x")
    monkeypatch.setattr(scanner, "resolve_folder", lambda name: d)
    logs = []
    names = {it[3].name for it in scanner.walk(["Downloads"], on_log=logs.append) if it[0] == "file"}
    assert names == {"setup.exe", "wcp.txt", "notas.txt"}
    assert len(logs) == 3
