"""La copia lleva todos los datos personales (y nada de claves) y se restaura con lo que dice su LEEME."""
import os
import subprocess
import tarfile

import copias


def test_copia_completa_y_restaurable(tmp_path, monkeypatch):
    base, local, destino = tmp_path / "panel", tmp_path / "local", tmp_path / "OneDrive" / "copias"
    (base / "cv").mkdir(parents=True); (local / "tarjetas").mkdir(parents=True); destino.parent.mkdir(parents=True)
    for nombre in ("agenda_data.json", "nuevo_modulo_data.json", "perfil.json", "carrera_semilla.json", "cv/cv.md", ".env", "panel.log"):
        (base / nombre).write_text("dato de " + nombre)
    (local / "estudio.json").write_text("{}"); (local / "tarjetas" / "a.png").write_bytes(b"png")
    (local / "fuentes.json").write_text("{}")
    monkeypatch.setattr(copias, "BASE", str(base)); monkeypatch.setattr(copias, "LOCAL", str(local))
    monkeypatch.setattr(copias, "DESTINO", str(destino)); monkeypatch.setattr(copias, "ESTADO", str(tmp_path / "estado.json"))

    est = copias.copiar("manual")
    fichero = destino / est["fichero"]
    with tarfile.open(fichero) as tar:
        nombres = set(tar.getnames())
    assert {"agenda_data.json", "nuevo_modulo_data.json", "perfil.json", "carrera_semilla.json", "cv/cv.md",
            "local-share/mipanelcontrol/estudio.json", "local-share/mipanelcontrol/tarjetas/a.png"} <= nombres
    assert not {".env", "panel.log", "local-share/mipanelcontrol/fuentes.json"} & nombres

    # restaurar con los dos comandos del LEEME
    panel2, share2 = tmp_path / "restaurado", tmp_path / "share"
    panel2.mkdir(); share2.mkdir()
    subprocess.run(["tar", "-xzf", fichero, "-C", panel2, "--exclude=local-share/*"], check=True)
    subprocess.run(["tar", "-xzf", fichero, "-C", share2, "--strip-components=1", "local-share"], check=True)
    assert (panel2 / "agenda_data.json").read_text() == "dato de agenda_data.json"
    assert not (panel2 / "local-share").exists()
    assert (share2 / "mipanelcontrol" / "tarjetas" / "a.png").read_bytes() == b"png"
