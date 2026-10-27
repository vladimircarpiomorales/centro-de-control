"""
Centro de Control PRO — resumen.py
Tu semana en números, comparada con la anterior, y un mensaje del coach.

Junta lo que guardan los demás módulos (no lleva datos propios salvo los
mensajes): candidaturas y entrevistas, contactos, horas de foco, estudio en
las plataformas, retos de laboratorio, subnetting, tarjetas, inglés y tareas
del plan de carrera. El domingo por la tarde genera el mensaje del coach
(Claude vía OmniRoute; si no, el modelo local) y avisa por notificación.
Mensajes en resumen_data.json (fuera de git).
"""

import datetime
import json
import os
import threading
import time

from status import log
import almacen

DATA_FILE = os.path.expanduser(os.environ.get("RESUMEN_DATA", "~/MiPanelControl/resumen_data.json"))
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("mensajes", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

def _lunes(dia: datetime.date) -> datetime.date:
    return dia - datetime.timedelta(days=dia.weekday())

def _en(fecha: str, ini: str, fin: str) -> bool:
    return bool(fecha) and ini <= fecha[:10] <= fin

def _suma_dias(dias: dict, ini: str, fin: str) -> int:
    return sum(v for k, v in (dias or {}).items() if _en(k, ini, fin))

def semana(lunes: datetime.date) -> dict:
    ini, fin = lunes.isoformat(), (lunes + datetime.timedelta(days=6)).isoformat()
    m = {}
    def seguro(nombre, fn):
        try:
            m[nombre] = fn()
        except Exception:
            m[nombre] = 0

    import ofertas, entrevistas, contactos, foco, retos, ingles, tarjetas, redes, carrera, agenda, estudio
    oitems = list(ofertas._load()["items"].values())
    seguro("postulaciones", lambda: sum(1 for it in oitems for h in it.get("historial", [])
                                        if h.get("estado") == "postulada" and _en(h.get("fecha", ""), ini, fin) and not h.get("seguimiento")))
    seguro("candidaturas", lambda: sum(1 for it in oitems if _en((it.get("preparacion") or {}).get("fecha", ""), ini, fin)))
    seguro("entrevistas_reales", lambda: sum(1 for e in agenda._load()["eventos"].values()
                                             if e["tipo"] == "entrevista" and _en(e["fecha"], ini, fin)))
    def _simuladas():
        ses = [s for s in entrevistas._load()["sesiones"].values() if _en(s["creada"], ini, fin)]
        notas = [s["informe"]["nota"] for s in ses if (s.get("informe") or {}).get("nota") is not None]
        m["nota_simulacros"] = round(sum(notas) / len(notas), 1) if notas else None
        return len(ses)
    seguro("simulacros", _simuladas)
    seguro("contactos", lambda: sum(1 for c in contactos._load()["contactos"].values() for h in c.get("historial", [])
                                    if _en(h["fecha"], ini, fin)))
    seguro("foco_min", lambda: sum(s["minutos"] for s in foco._load()["sesiones"] if _en(s["fecha"], ini, fin)))
    seguro("retos", lambda: sum(1 for f in retos._load()["hechos"].values() if _en(f, ini, fin)))
    seguro("ingles", lambda: _suma_dias(ingles._load()["historial"], ini, fin))
    seguro("tarjetas", lambda: _suma_dias(tarjetas._load()["historial"], ini, fin))
    seguro("subnetting", lambda: _suma_dias(redes._load()["subnetting"].get("dias", {}), ini, fin))
    def _plataformas():
        diario = estudio._estado().get("diario", {})
        dias = sorted(diario)
        antes = [diario[k] for k in dias if k < ini]
        dentro = [diario[k] for k in dias if _en(k, ini, fin)]
        return max(0, dentro[-1] - (antes[-1] if antes else dentro[0])) if dentro else 0
    seguro("plataformas", _plataformas)
    cdat = carrera._load()
    seguro("tareas", lambda: sum(1 for f in cdat["fases"] for o in f["objetivos"] for t in o["tareas"]
                                 if t.get("done") and _en(t.get("done_date") or "", ini, fin)))
    seguro("logros", lambda: sum(1 for l in cdat["logros"] if _en(l.get("fecha", ""), ini, fin) and not l.get("seed")))
    m.setdefault("nota_simulacros", None)
    return {"inicio": ini, "fin": fin, "datos": m}

ETIQUETAS = [
    ("postulaciones", "📨", "postulaciones"), ("candidaturas", "📝", "candidaturas preparadas"),
    ("entrevistas_reales", "🎤", "entrevistas reales"), ("simulacros", "🎙", "entrevistas de práctica"),
    ("contactos", "🤝", "mensajes a contactos"), ("foco_min", "⏱", "minutos de foco"),
    ("plataformas", "📚", "unidades y preguntas en tus plataformas"), ("retos", "🧪", "labs hechos"),
    ("subnetting", "🧮", "ejercicios de subnetting"), ("tarjetas", "🃏", "tarjetas repasadas"),
    ("ingles", "🇬🇧", "repasos de inglés"), ("tareas", "🚀", "tareas del plan"), ("logros", "🏆", "logros nuevos"),
]

PROMPT = """Eres el coach de carrera de {nombre}. {contexto}
Escribe su resumen de la semana en español, de tú, 70-110 palabras: honesto, cercano y concreto.
1) Lo que SÍ hizo esta semana (cita 2-3 cifras de abajo). 2) Una comparación breve con la semana anterior.
3) UNA sola propuesta concreta para la semana que viene, la palanca más útil para conseguir trabajo.
Sin frases vacías de autoayuda ni exclamaciones en cada frase. No inventes nada que no esté en los datos.
Responde SOLO en JSON: {{"mensaje": "..."}}

ESTA SEMANA ({ini} a {fin}): {esta}
SEMANA ANTERIOR: {anterior}
META: {meta} postulaciones por semana.
"""

def generar(lunes: datetime.date = None) -> dict:
    import candidatura, ofertas
    lunes = lunes or _lunes(datetime.date.today())
    esta, anterior = semana(lunes), semana(lunes - datetime.timedelta(days=7))
    leer = lambda s: ", ".join(f"{texto}: {s['datos'].get(k)}" for k, _, texto in ETIQUETAS if s["datos"].get(k)) or "nada registrado"
    prompt = PROMPT.format(nombre=candidatura.PERFIL.get("nombre", "la persona"), contexto=candidatura.PERFIL.get("coach_contexto", ""),
                           ini=esta["inicio"], fin=esta["fin"], esta=leer(esta), anterior=leer(anterior), meta=ofertas.META_SEMANAL)
    try:
        candidatura._omniroute_listo()
        r = candidatura._chat_omniroute(prompt)
    except Exception:
        try:
            r = candidatura._chat_local(prompt)
        except Exception as e:
            return {"error": f"No pude generar el mensaje ({str(e)[:100]})"}
    msg = str(r.get("mensaje", "")).strip()[:1200]
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        d["mensajes"][esta["inicio"]] = {"fecha": datetime.datetime.now().isoformat(timespec="minutes"), "mensaje": msg}
        _save(d)
    return {"mensaje": msg}

def get_data() -> dict:
    lunes = _lunes(datetime.date.today())
    esta, anterior = semana(lunes), semana(lunes - datetime.timedelta(days=7))
    d = _load()
    filas = [{"clave": k, "icono": i, "texto": t, "esta": esta["datos"].get(k) or 0, "anterior": anterior["datos"].get(k) or 0}
             for k, i, t in ETIQUETAS]
    ultimo = d["mensajes"].get(esta["inicio"]) or d["mensajes"].get(anterior["inicio"])
    return {"esta": esta, "anterior": anterior, "filas": filas, "nota_simulacros": esta["datos"].get("nota_simulacros"),
            "mensaje": ultimo, "historial": sorted(d["mensajes"].items(), reverse=True)[:8]}

def _bucle():
    time.sleep(240)
    while True:
        try:
            ahora = datetime.datetime.now()
            lunes = _lunes(ahora.date()).isoformat()
            if ahora.weekday() == 6 and ahora.hour >= 19 and lunes not in _load()["mensajes"]:
                r = generar()
                if r.get("mensaje"):
                    log("📊 Resumen de la semana listo")
                    try:
                        from plyer import notification as _n
                        _n.notify(title="📊 Tu semana", message=r["mensaje"][:240], timeout=20)
                    except Exception:
                        pass
        except Exception as e:
            log(f"⚠ Resumen semanal: {e}")
        time.sleep(1800)

def start_resumen():
    threading.Thread(target=_bucle, daemon=True).start()
