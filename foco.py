"""
Centro de Control PRO — foco.py
Modo foco (pomodoro): bloques de 25 o 50 minutos con una materia, y registro de
horas reales de estudio y de búsqueda de empleo.

La sesión en curso vive en el servidor (sobrevive a recargar la ventana); un
hilo avisa al terminar el bloque y al terminar el descanso. Una sesión cortada
antes de tiempo cuenta los minutos hechos si pasan de 5.
Datos en foco_data.json (fuera de git).
"""

import datetime
import json
import os
import threading
import time

from extensions import socketio
from status import log
import almacen

DATA_FILE = os.path.expanduser(os.environ.get("FOCO_DATA", "~/MiPanelControl/foco_data.json"))
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("sesiones", [])
    d.setdefault("actual", None)
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=None)

def _avisar(titulo, texto):
    log(f"⏱ {titulo}: {texto}")
    try:
        from plyer import notification as _n
        _n.notify(title=titulo, message=texto, timeout=10)
    except Exception:
        pass
    try:
        socketio.emit("foco", {"evento": titulo})
    except Exception:
        pass

def materias() -> list:
    base = ["AZ-104", "Inglés", "Redes / subnetting", "Búsqueda de empleo", "Laboratorio práctico"]
    try:
        import estudio
        cursos = [c["nombre"] for c in estudio.get_data()["cursos"] if c["codigo"] != "az104"]
    except Exception:
        cursos = []
    return base[:1] + cursos + base[1:] + ["Otro"]

@_exclusivo
def empezar(materia: str, minutos: int = 25) -> dict:
    minutos = 50 if int(minutos) == 50 else 25
    d = _load()
    if d["actual"]:
        terminar(False)
        d = _load()
    d["actual"] = {"materia": str(materia).strip()[:60] or "Otro", "minutos": minutos,
                   "inicio": time.time(), "fin": time.time() + minutos * 60,
                   "descanso": 10 if minutos == 50 else 5, "avisado": False}
    _save(d)
    return d["actual"]

@_exclusivo
def terminar(completa: bool = True) -> dict:
    d = _load()
    a = d["actual"]
    if not a:
        return {}
    hechos = round(min(a["minutos"], (time.time() - a["inicio"]) / 60))
    if completa or hechos >= 5:
        d["sesiones"].append({"fecha": datetime.date.fromtimestamp(a["inicio"]).isoformat(),
                              "hora": datetime.datetime.fromtimestamp(a["inicio"]).strftime("%H:%M"),
                              "materia": a["materia"], "minutos": a["minutos"] if completa else hechos,
                              "completa": bool(completa)})
        d["sesiones"] = d["sesiones"][-2000:]
    d["actual"] = None
    _save(d)
    return {"minutos": hechos}

def get_data() -> dict:
    d = _load()
    hoy = datetime.date.today()
    lunes = (hoy - datetime.timedelta(days=hoy.weekday())).isoformat()
    ses = d["sesiones"]
    semana = {}
    for s in ses:
        if s["fecha"] >= lunes:
            semana[s["materia"]] = semana.get(s["materia"], 0) + s["minutos"]
    dias = {s["fecha"] for s in ses if s["minutos"] >= 20}
    racha, dia = 0, hoy if hoy.isoformat() in dias else hoy - datetime.timedelta(days=1)
    while dia.isoformat() in dias:
        racha += 1
        dia -= datetime.timedelta(days=1)
    a = d["actual"]
    if a:
        a = {**a, "restante": max(0, int(a["fin"] - time.time()))}
    return {"actual": a, "hoy_min": sum(s["minutos"] for s in ses if s["fecha"] == hoy.isoformat()),
            "semana": dict(sorted(semana.items(), key=lambda kv: -kv[1])), "semana_min": sum(semana.values()),
            "racha": racha, "materias": materias(), "recientes": ses[-8:][::-1]}

def _bucle():
    while True:
        try:
            with _lock:   # marcar «avisado» sin pisar un empezar/terminar de la interfaz
                d = _load()
                a = d["actual"]
                toca = bool(a and not a.get("avisado") and time.time() >= a["fin"])
                if toca:
                    a["avisado"] = True
                    _save(d)
            if toca:
                terminar(True)
                _avisar("⏱ ¡Bloque terminado!", f"{a['minutos']} min de {a['materia']}. Descansa {a['descanso']} minutos: levántate, agua, ojos lejos de la pantalla.")
                time.sleep(a["descanso"] * 60)
                _avisar("⏱ Fin del descanso", "¿Otro bloque? Pulsa ⏱ en el panel cuando quieras.")
        except Exception as e:
            log(f"⚠ Modo foco: {e}")
        time.sleep(5)

def start_foco():
    threading.Thread(target=_bucle, daemon=True).start()
