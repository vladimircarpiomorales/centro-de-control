"""Agenda: guardar, avisos en su momento y exportación .ics."""
import datetime

import pytest

import agenda


@pytest.fixture(autouse=True)
def fichero_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(agenda, "DATA_FILE", str(tmp_path / "agenda.json"))
    monkeypatch.setattr(agenda, "_examen_estudio", lambda: [])
    avisos = []
    monkeypatch.setattr(agenda, "_notificar", lambda t, x: avisos.append((t, x)))
    return avisos


def test_rechaza_fecha_mala():
    with pytest.raises(ValueError):
        agenda.guardar({"titulo": "x", "fecha": "31-02-2026"})


def test_proximos_y_aviso_de_una_hora(fichero_temporal):
    dentro = datetime.datetime.now() + datetime.timedelta(minutes=40)
    agenda.guardar({"titulo": "Entrevista", "tipo": "entrevista", "fecha": dentro.date().isoformat(),
                    "hora": dentro.strftime("%H:%M")})
    assert agenda.get_data()["proximos"][0]["titulo"] == "Entrevista"
    agenda._revisar_avisos()
    agenda._revisar_avisos()                    # no repite
    assert sum(1 for t, _ in fichero_temporal if "hora" in t) == 1


def test_ics_valido():
    agenda.guardar({"titulo": "Examen, AZ-104", "tipo": "examen", "fecha": "2026-12-01"})
    texto = agenda.ics()
    assert texto.startswith("BEGIN:VCALENDAR") and "DTSTART;VALUE=DATE:20261201" in texto
    assert "Examen\\, AZ-104" in texto
