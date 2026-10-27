"""
Centro de Control PRO — carrera.py
Plan de carrera profesional del usuario: fases con tareas marcables, registro de
logros y coach IA local (Ollama) que evalúa el progreso y motiva.

Los datos persisten en carrera_data.json. La primera vez se siembra el plan
completo (Fase 1 Consolidación → Fase 2 Especialización → Fase 3 Posicionamiento)
y los logros ya conseguidos, para que el panel nunca arranque "en cero".
"""

import datetime
import hashlib
import json
import os
import threading

from extensions import socketio
from status import log
from rag import _ollama_post
import almacen

DATA_FILE = os.path.expanduser(os.environ.get("CARRERA_DATA", "~/MiPanelControl/carrera_data.json"))
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)

MODELO_COACH_DEFAULT = "llama3.1"


# ─── Plan semilla ───────────────────────────────────────────────────────────────
# Solo se usa la primera vez (luego todo vive en carrera_data.json). El plan propio
# está en carrera_semilla.json (privado); sin él, el de ejemplo.
SEMILLA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "carrera_semilla.json")

def _semilla() -> dict:
    ruta = SEMILLA_FILE if os.path.isfile(SEMILLA_FILE) else SEMILLA_FILE.replace(".json", ".example.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _hoy() -> str:
    return datetime.date.today().isoformat()


def _seed() -> dict:
    sem = _semilla()
    logros = [
        {"id": hashlib.md5(l["texto"].encode()).hexdigest()[:10], "fecha": l["fecha"], "texto": l["texto"], "seed": True}
        for l in sem.get("logros", [])
    ]
    return {
        "perfil": sem.get("perfil", ""),
        "meta": sem.get("meta", ""),
        "fases": sem.get("fases", []),
        "logros": logros,
        "coach_history": [],
        "created": _hoy(),
    }


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        data = _seed()
        _save(data)
        log("🚀 Plan de carrera sembrado por primera vez")
        return data


def _save(data: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, data, indent=1)


# ─── Estadísticas ───────────────────────────────────────────────────────────────
def _stats(data: dict) -> dict:
    total = hechas = semana = 0
    ultimo = None
    hoy = datetime.date.today()
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            for t in obj["tareas"]:
                total += 1
                if t["done"]:
                    hechas += 1
                    if t.get("done_date"):
                        d = datetime.date.fromisoformat(t["done_date"])
                        if (hoy - d).days <= 7:
                            semana += 1
                        if ultimo is None or d > ultimo:
                            ultimo = d
    for lg in data["logros"]:
        if not lg.get("seed"):
            d = datetime.date.fromisoformat(lg["fecha"])
            if (hoy - d).days <= 7:
                semana += 1
            if ultimo is None or d > ultimo:
                ultimo = d
    return {
        "total": total,
        "hechas": hechas,
        "pct": round(hechas * 100 / total) if total else 0,
        "semana": semana,
        "ultimo_avance": ultimo.isoformat() if ultimo else None,
        "dias_sin_avance": (hoy - ultimo).days if ultimo else None,
    }


def get_data() -> dict:
    data = _load()
    return {**data, "stats": _stats(data)}


# ─── Acciones ───────────────────────────────────────────────────────────────────
@_exclusivo
def toggle_tarea(tarea_id: str) -> bool:
    data = _load()
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            for t in obj["tareas"]:
                if t["id"] == tarea_id:
                    t["done"] = not t["done"]
                    t["done_date"] = _hoy() if t["done"] else None
                    _save(data)
                    if t["done"]:
                        log(f"✅ Avance de carrera: {t['texto'][:70]}")
                        if t.get("hito"):
                            log("🏆 ¡HITO CONSEGUIDO! Regístralo también en tus logros.")
                    return True
    return False


@_exclusivo
def add_tarea(objetivo_id: str, texto: str) -> bool:
    texto = texto.strip()
    if not texto:
        return False
    data = _load()
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            if obj["id"] == objetivo_id:
                tid = "custom-" + hashlib.md5((texto + _hoy()).encode()).hexdigest()[:8]
                obj["tareas"].append({"id": tid, "texto": texto, "hito": False,
                                      "done": False, "done_date": None, "custom": True})
                _save(data)
                return True
    return False


@_exclusivo
def del_tarea(tarea_id: str) -> bool:
    if not tarea_id.startswith("custom-"):
        return False           # solo se borran las tareas añadidas a mano, no el plan
    data = _load()
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            antes = len(obj["tareas"])
            obj["tareas"] = [t for t in obj["tareas"] if t["id"] != tarea_id]
            if len(obj["tareas"]) != antes:
                _save(data)
                return True
    return False


@_exclusivo
def add_logro(texto: str) -> bool:
    texto = texto.strip()
    if not texto:
        return False
    data = _load()
    lid = hashlib.md5((texto + _hoy()).encode()).hexdigest()[:10]
    data["logros"].insert(0, {"id": lid, "fecha": _hoy(), "texto": texto})
    _save(data)
    log(f"🏆 Nuevo logro registrado: {texto[:70]}")
    return True


@_exclusivo
def del_logro(logro_id: str) -> bool:
    data = _load()
    antes = len(data["logros"])
    data["logros"] = [l for l in data["logros"] if l["id"] != logro_id]
    if len(data["logros"]) != antes:
        _save(data)
        return True
    return False


# ─── Coach IA ───────────────────────────────────────────────────────────────────
def _contexto_coach(data: dict, stats: dict) -> str:
    hoy = datetime.date.today()
    partes = [f"FECHA DE HOY: {hoy.isoformat()}", f"PERFIL: {data['perfil']}",
              f"META: {data['meta']}",
              f"PROGRESO GLOBAL: {stats['hechas']}/{stats['total']} tareas ({stats['pct']}%). "
              f"Avances en los últimos 7 días: {stats['semana']}. "
              + (f"Días desde el último avance: {stats['dias_sin_avance']}." if stats['dias_sin_avance'] is not None
                 else "Aún sin avances registrados.")]

    for fase in data["fases"]:
        lineas = []
        for obj in fase["objetivos"]:
            done = sum(1 for t in obj["tareas"] if t["done"])
            lineas.append(f"  - {obj['titulo']}: {done}/{len(obj['tareas'])}")
        partes.append(f"{fase['titulo']} ({fase['periodo']}):\n" + "\n".join(lineas))

    recientes = []
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            for t in obj["tareas"]:
                if t["done"] and t.get("done_date") and \
                   (hoy - datetime.date.fromisoformat(t["done_date"])).days <= 21:
                    recientes.append(f"  - [{t['done_date']}] {t['texto']}")
    if recientes:
        partes.append("COMPLETADO EN LAS ÚLTIMAS 3 SEMANAS:\n" + "\n".join(recientes[:10]))

    pendientes = []
    for fase in data["fases"]:
        for obj in fase["objetivos"]:
            for t in obj["tareas"]:
                if not t["done"] and len(pendientes) < 6:
                    pendientes.append(f"  - ({obj['titulo']}) {t['texto']}")
        if pendientes:
            break              # solo la primera fase con trabajo pendiente
    partes.append("PRÓXIMAS TAREAS PENDIENTES:\n" + "\n".join(pendientes))

    logros = [f"  - [{l['fecha']}] {l['texto']}" for l in data["logros"][:8]]
    partes.append("LOGROS REGISTRADOS (los más recientes):\n" + "\n".join(logros))
    return "\n\n".join(partes)


import perfil as _perfil
_P = _perfil.get()
PROMPT_COACH = (
    f"Eres el coach de carrera personal de {_P.get('nombre', 'la persona usuaria')}. Le hablas de tú, en español, con cercanía "
    "y honestidad — como un buen amigo que además es mentor técnico senior. "
    f"{_P.get('coach_contexto', '')} "
    "Tu trabajo NO es adularle: es mostrarle con sus propios datos que avanza, y darle foco.\n\n"
    "Usando ÚNICAMENTE los datos de abajo, responde con esta estructura (máximo 250 palabras):\n"
    "1. **Cómo vas** — evaluación honesta en 2-3 frases del ritmo actual.\n"
    "2. **Lo que ya has demostrado** — recuérdale 2-3 logros o avances concretos SUYOS (de los datos).\n"
    "3. **Tu siguiente paso** — elige UNA sola tarea pendiente de la lista y explica por qué esa "
    "es la palanca esta semana.\n"
    "4. Cierre breve y motivador, sin frases vacías de autoayuda.\n\n"
    "Si lleva muchos días sin avances, dilo sin dramatizar y propón un paso pequeño para retomar. "
    "No inventes datos que no estén abajo.\n\n"
)


def coach(modelo: str = MODELO_COACH_DEFAULT):
    """Pide al modelo local una evaluación del progreso. Corre en background (run_bg)
    y emite el resultado por socket; también lo persiste en coach_history."""
    data  = _load()
    stats = _stats(data)
    log(f"🧠 Coach de carrera pensando con {modelo}...")
    try:
        r = _ollama_post("/api/chat", {
            "model": modelo,
            "messages": [{"role": "user", "content": PROMPT_COACH + _contexto_coach(data, stats)}],
            "stream": False,
        }, timeout=420)
        texto = r.get("message", {}).get("content", "").strip() or "(el modelo no devolvió respuesta)"
    except Exception as e:
        msg = ("⚠ No pude hablar con Ollama. Enciende «Ollama (motor IA)» en la pestaña "
               f"Locales y vuelve a intentarlo. ({e})")
        log(msg)
        socketio.emit("carrera_coach", {"error": True, "texto": msg})
        return

    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        data = _load()   # en los minutos que tarda la IA pueden haber cambiado tareas o logros
        entry = {"fecha": _hoy(), "modelo": modelo, "texto": texto}
        data["coach_history"].append(entry)
        data["coach_history"] = data["coach_history"][-20:]
        _save(data)
    log("🧠 Coach de carrera: evaluación lista")
    socketio.emit("carrera_coach", entry)
