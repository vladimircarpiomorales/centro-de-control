"""Los datos no se pierden ni se rompen: escritura atómica y «leer, cambiar y guardar» en exclusiva."""
import json
import threading
import time

import pytest

import almacen


def test_guardado_cortado_deja_el_archivo_anterior(tmp_path):
    ruta = tmp_path / "datos.json"
    almacen.guardar_json(str(ruta), {"bueno": 1})

    class Rompe:   # json.dump falla a mitad de escribir
        pass
    with pytest.raises(TypeError):
        almacen.guardar_json(str(ruta), {"a": 1, "b": Rompe()})
    assert json.loads(ruta.read_text()) == {"bueno": 1}


def test_veinte_eventos_a_la_vez_no_se_pisan(tmp_path, monkeypatch):
    import agenda
    monkeypatch.setattr(agenda, "DATA_FILE", str(tmp_path / "agenda.json"))
    hilos = [threading.Thread(target=agenda.guardar, args=({"fecha": "2026-11-0%d" % (1 + i % 9), "titulo": f"evento {i}"},))
             for i in range(20)]
    for h in hilos: h.start()
    for h in hilos: h.join()
    assert len(json.loads((tmp_path / "agenda.json").read_text())["eventos"]) == 20


def test_coach_no_borra_lo_que_apuntas_mientras_piensa(tmp_path, monkeypatch):
    import carrera
    monkeypatch.setattr(carrera, "DATA_FILE", str(tmp_path / "carrera.json"))
    monkeypatch.setattr(carrera.socketio, "emit", lambda *a, **k: None)
    carrera.get_data()                                    # siembra el plan

    def ia_lenta(*a, **k):
        time.sleep(0.3)
        return {"message": {"content": "vas bien"}}
    monkeypatch.setattr(carrera, "_ollama_post", ia_lenta)
    hilo = threading.Thread(target=carrera.coach); hilo.start()
    time.sleep(0.1)
    carrera.add_logro("logro apuntado mientras el coach piensa")
    hilo.join()
    d = json.loads((tmp_path / "carrera.json").read_text())
    assert any(l["texto"] == "logro apuntado mientras el coach piensa" for l in d["logros"])
    assert d["coach_history"][-1]["texto"] == "vas bien"
