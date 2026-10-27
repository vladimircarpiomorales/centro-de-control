"""Tareas en segundo plano: sin duplicados y con un máximo a la vez."""
import threading
import time

import status


def _esperar(cond, segundos=3):
    fin = time.time() + segundos
    while time.time() < fin and not cond():
        time.sleep(0.01)
    return cond()


def test_misma_clave_no_se_lanza_dos_veces(monkeypatch):
    avisos = []; monkeypatch.setattr(status, "log", avisos.append)
    suelta = threading.Event(); hechas = []
    trabajo = lambda: (suelta.wait(2), hechas.append(1))
    assert status.run_bg(trabajo, clave="prueba", que="La prueba") is True
    assert status.run_bg(trabajo, clave="prueba", que="La prueba") is False
    assert any("ya está en marcha" in a for a in avisos)
    suelta.set()
    assert _esperar(lambda: "La prueba" not in status.tareas_en_marcha())
    assert status.run_bg(lambda: None, clave="prueba") is True      # terminada: se puede volver a lanzar


def test_nunca_mas_de_max_tareas_a_la_vez(monkeypatch):
    monkeypatch.setattr(status, "log", lambda m: None)
    activas, pico, terminadas, cerrojo = [0], [0], [], threading.Lock()
    def trabajo():
        with cerrojo:
            activas[0] += 1; pico[0] = max(pico[0], activas[0])
        time.sleep(0.15)
        with cerrojo:
            activas[0] -= 1; terminadas.append(1)
    for _ in range(status.MAX_TAREAS + 3):
        status.run_bg(trabajo)
    assert _esperar(lambda: len(terminadas) == status.MAX_TAREAS + 3)
    assert pico[0] <= status.MAX_TAREAS


def test_un_fallo_se_avisa_y_libera_la_clave(monkeypatch):
    avisos = []; monkeypatch.setattr(status, "log", avisos.append)
    def rompe():
        raise RuntimeError("se rompió")
    status.run_bg(rompe, clave="rota", que="La tarea rota")
    assert _esperar(lambda: any("se rompió" in a for a in avisos))
    assert _esperar(lambda: "La tarea rota" not in status.tareas_en_marcha())
