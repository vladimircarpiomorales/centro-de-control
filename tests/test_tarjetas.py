"""Tarjetas: validación de la imagen, guardado y repaso espaciado (sin red)."""
import base64

import pytest

import tarjetas


@pytest.fixture(autouse=True)
def temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(tarjetas, "DATA_FILE", str(tmp_path / "t.json"))


def test_rechaza_lo_que_no_es_imagen():
    assert tarjetas.proponer(base64.b64encode(b"<script>").decode())["error"]
    assert tarjetas.proponer("no-es-base64!!")["error"]
    assert tarjetas.proponer()["error"]


def test_guardar_y_repasar():
    assert tarjetas.guardar([{"pregunta": "¿Es transitivo el peering?", "respuesta": "No"}, {"pregunta": "", "respuesta": "x"}],
                            "AZ-104", imagen="../../etc/passwd") == 1
    d = tarjetas.get_data()
    t = d["cola"][0]
    assert t["imagen"] == "" and t["caja"] == 0
    assert tarjetas.repasar(t["id"], True)
    assert tarjetas.get_data()["cola"] == []          # pasa a mañana
