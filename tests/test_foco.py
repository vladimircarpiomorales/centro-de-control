"""Modo foco: qué cuenta y qué no."""
import pytest

import foco


@pytest.fixture(autouse=True)
def temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(foco, "DATA_FILE", str(tmp_path / "foco.json"))
    monkeypatch.setattr(foco, "materias", lambda: ["AZ-104"])


def test_cortar_enseguida_no_cuenta():
    foco.empezar("AZ-104", 25)
    foco.terminar(False)
    assert foco.get_data()["hoy_min"] == 0


def test_bloque_completo_cuenta_y_hace_racha():
    foco.empezar("AZ-104", 25)
    foco.terminar(True)
    d = foco.get_data()
    assert d["hoy_min"] == 25 and d["semana"] == {"AZ-104": 25} and d["racha"] == 1
