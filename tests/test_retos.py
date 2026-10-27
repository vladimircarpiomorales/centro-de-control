"""Reto del día: se elige de lo que hay y solo se abren rutas del catálogo."""
import json

import retos


def test_catalogo_y_rutas(tmp_path, monkeypatch):
    (tmp_path / "ccna-labs" / "labs").mkdir(parents=True)
    (tmp_path / "ccna-labs" / "labs" / "cs-112-vlan-basics-3.html").write_text("<html></html>")
    (tmp_path / "az104-2026" / "build" / "labs").mkdir(parents=True)
    (tmp_path / "az104-2026" / "build" / "labs" / "LAB_07-Manage_Azure_Storage.md").write_text("# Lab")
    monkeypatch.setattr(retos, "PROYECTOS", str(tmp_path))
    monkeypatch.setattr(retos, "DATA_FILE", str(tmp_path / "retos.json"))
    cat = {r["id"]: r for r in retos.catalogo()}
    assert cat["ccna:cs-112-vlan-basics-3"]["titulo"] == "VLAN basics"
    assert cat["azure:LAB_07"]["titulo"] == "Manage Azure storage"
    assert retos.ruta_de("azure:LAB_07").endswith(".md")
    assert retos.ruta_de("../../etc/passwd") == ""
    assert not retos.marcar_hecho("linux:inventado")
    assert retos.marcar_hecho("azure:LAB_07")
    assert "azure:LAB_07" in json.load(open(tmp_path / "retos.json"))["hechos"]
