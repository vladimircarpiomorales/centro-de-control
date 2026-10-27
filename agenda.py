"""
Centro de Control PRO — agenda.py
Fechas que no se pueden escapar: entrevistas, exámenes, plazos de becas,
trámites (CCSE, nacionalidad, NIE…) y bloques de estudio.

Avisa por notificación de escritorio la víspera, el mismo día por la mañana y
una hora antes (si el evento tiene hora). El examen de «Tu estudio» aparece
también aquí. Exporta a .ics para el calendario del móvil.
Datos en agenda_data.json (fuera de git).
"""

import datetime
import json
import os
import threading
import time
import uuid

from status import log
import almacen

DATA_FILE = os.path.expanduser(os.environ.get("AGENDA_DATA", "~/MiPanelControl/agenda_data.json"))
TIPOS     = {"entrevista": "🎤", "examen": "📝", "beca": "🎓", "tramite": "🏛", "estudio": "📚", "otro": "📌"}
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("eventos", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

def _valida(fecha: str, hora: str) -> tuple:
    datetime.date.fromisoformat(fecha)
    if hora:
        datetime.time.fromisoformat(hora)
    return fecha, hora

@_exclusivo
def guardar(ev: dict) -> str:
    fecha, hora = _valida(str(ev.get("fecha", "")), str(ev.get("hora", "") or ""))
    tipo = ev.get("tipo") if ev.get("tipo") in TIPOS else "otro"
    d = _load()
    eid = str(ev.get("id") or "") if str(ev.get("id") or "") in d["eventos"] else uuid.uuid4().hex[:10]
    previo = d["eventos"].get(eid, {})
    d["eventos"][eid] = {
        "id": eid, "fecha": fecha, "hora": hora, "tipo": tipo,
        "titulo": str(ev.get("titulo", "")).strip()[:120] or TIPOS[tipo] + " " + tipo,
        "lugar": str(ev.get("lugar", "")).strip()[:200], "nota": str(ev.get("nota", "")).strip()[:600],
        "oferta_id": ev.get("oferta_id") or previo.get("oferta_id"),
        "hecho": bool(ev.get("hecho", previo.get("hecho", False))),
        # si cambia la fecha o la hora, se vuelve a avisar
        "avisado": previo.get("avisado", []) if (previo.get("fecha"), previo.get("hora")) == (fecha, hora) else [],
    }
    _save(d)
    return eid

@_exclusivo
def borrar(eid: str) -> bool:
    d = _load()
    if d["eventos"].pop(eid, None) is None:
        return False
    _save(d)
    return True

@_exclusivo
def hecho(eid: str, valor: bool) -> bool:
    d = _load()
    if eid not in d["eventos"]:
        return False
    d["eventos"][eid]["hecho"] = bool(valor)
    _save(d)
    return True

def _examen_estudio() -> list:
    try:
        import estudio
        ex = estudio._estado().get("examen")
        if ex and ex.get("fecha"):
            return [{"id": "examen-estudio", "fecha": ex["fecha"], "hora": "", "tipo": "examen",
                     "titulo": ex.get("nombre", "Examen"), "lugar": "", "nota": "Desde «Tu estudio»",
                     "solo_lectura": True, "hecho": False}]
    except Exception:
        pass
    return []

def get_data() -> dict:
    hoy = datetime.date.today()
    evs = list(_load()["eventos"].values()) + _examen_estudio()
    for e in evs:
        e["dias"] = (datetime.date.fromisoformat(e["fecha"]) - hoy).days
        e["icono"] = TIPOS.get(e["tipo"], "📌")
    evs.sort(key=lambda e: (e["fecha"], e.get("hora") or "99"))
    return {"eventos": evs, "proximos": [e for e in evs if 0 <= e["dias"] <= 7 and not e.get("hecho")],
            "tipos": TIPOS, "hoy": hoy.isoformat()}


# ─── Avisos ────────────────────────────────────────────────────────────────────
def _notificar(titulo: str, texto: str):
    log(f"🗓 {titulo}: {texto}")
    try:
        from plyer import notification as _n
        _n.notify(title=titulo, message=texto[:240], timeout=15)
    except Exception:
        pass

@_exclusivo
def _revisar_avisos():
    ahora = datetime.datetime.now()
    d = _load()
    cambios = False
    for e in d["eventos"].values():
        if e.get("hecho"):
            continue
        dia = datetime.date.fromisoformat(e["fecha"])
        cuando = datetime.datetime.combine(dia, datetime.time.fromisoformat(e["hora"])) if e.get("hora") else None
        avisos = e.setdefault("avisado", [])
        quien = f"{TIPOS.get(e['tipo'], '')} {e['titulo']}" + (f" a las {e['hora']}" if e.get("hora") else "")
        if dia - ahora.date() == datetime.timedelta(days=1) and ahora.hour >= 18 and "vispera" not in avisos:
            _notificar("🗓 Mañana", quien + (f" · {e['lugar']}" if e.get("lugar") else ""))
            avisos.append("vispera"); cambios = True
        if dia == ahora.date() and ahora.hour >= 8 and "dia" not in avisos:
            _notificar("🗓 Hoy", quien)
            avisos.append("dia"); cambios = True
        if cuando and datetime.timedelta(0) <= cuando - ahora <= datetime.timedelta(hours=1) and "hora" not in avisos:
            _notificar("⏰ En menos de una hora", quien + (f" · {e['lugar']}" if e.get("lugar") else ""))
            avisos.append("hora"); cambios = True
    if cambios:
        _save(d)

def _bucle():
    time.sleep(45)
    while True:
        try:
            _revisar_avisos()
        except Exception as ex:
            log(f"⚠ Agenda: {ex}")
        time.sleep(600)

def start_agenda():
    threading.Thread(target=_bucle, daemon=True).start()


# ─── Exportar ──────────────────────────────────────────────────────────────────
def ics() -> str:
    def esc(t):
        return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Centro de Control PRO//Agenda//ES", "CALSCALE:GREGORIAN"]
    sello = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in get_data()["eventos"]:
        f = e["fecha"].replace("-", "")
        lineas += ["BEGIN:VEVENT", f"UID:{e['id']}@centro-de-control", f"DTSTAMP:{sello}"]
        if e.get("hora"):
            inicio = f + "T" + e["hora"].replace(":", "") + "00"
            fin = (datetime.datetime.strptime(inicio, "%Y%m%dT%H%M%S") + datetime.timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
            lineas += [f"DTSTART;TZID=Europe/Madrid:{inicio}", f"DTEND;TZID=Europe/Madrid:{fin}"]
        else:
            sig = (datetime.date.fromisoformat(e["fecha"]) + datetime.timedelta(days=1)).strftime("%Y%m%d")
            lineas += [f"DTSTART;VALUE=DATE:{f}", f"DTEND;VALUE=DATE:{sig}"]
        lineas.append(f"SUMMARY:{esc(e['icono'] + ' ' + e['titulo'])}")
        if e.get("lugar"):
            lineas.append(f"LOCATION:{esc(e['lugar'])}")
        if e.get("nota"):
            lineas.append(f"DESCRIPTION:{esc(e['nota'])}")
        lineas += ["BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", f"DESCRIPTION:{esc(e['titulo'])}", "END:VALARM", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas) + "\r\n"
