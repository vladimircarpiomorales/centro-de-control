"""
Centro de Control PRO — entrevistas.py
Simulador de entrevistas por voz.

Eliges una oferta (o una entrevista general de sistemas) y el idioma. Claude
(vía OmniRoute, como las candidaturas) hace de entrevistador: una pregunta cada
vez, con alguna repregunta si la respuesta queda vaga. Tú contestas HABLANDO
(se graba el micrófono y Whisper lo pasa a texto; también puedes escribir).
Al terminar, un informe: nota por respuesta, qué estuvo bien, qué mejorar, una
versión mejorada con hechos REALES de tu CV y, en inglés, correcciones.

Las sesiones se guardan en entrevistas_data.json (fuera de git) para ver la
evolución. Las grabaciones quedan en ~/.cache/mipanelcontrol/entrevistas (para
escucharte), 30 días.
"""

import datetime
import json
import os
import re
import threading
import time
import uuid

from extensions import socketio
from status import log
import candidatura
import voz
import almacen

DATA_FILE   = os.path.expanduser(os.environ.get("ENTREVISTAS_DATA", "~/MiPanelControl/entrevistas_data.json"))
GRABACIONES = os.path.expanduser("~/.cache/mipanelcontrol/entrevistas")
_lock       = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)
grabadora   = voz.Grabadora()
UMBRAL_SILENCIO = float(os.environ.get("UMBRAL_SILENCIO", 120))   # RMS; habla normal con los cascos: >500

GENERICA = {"titulo": "Técnico / Administrador de Sistemas", "empresa": "una empresa de Madrid",
            "descripcion": "Puesto de administrador de sistemas: Windows Server y Active Directory, Linux, "
                           "virtualización VMware, redes (VLAN, switching, WiFi), Microsoft 365 y Azure, soporte "
                           "N2, gestión de incidencias por tickets, copias de seguridad y documentación."}

PROMPT_TURNO = """Eres {quien} en una entrevista de trabajo REAL para este puesto en Madrid. {estilo}
Haz UNA sola intervención cada vez (máximo 2-3 frases), como en una conversación de verdad.
- Si es el principio, saluda en una frase y haz la primera pregunta.
- Si la última respuesta fue vaga o muy corta, puedes hacer UNA repregunta concreta («¿Me pones un ejemplo?»).
- Mezcla preguntas técnicas del puesto, de experiencia (situaciones reales) y una de motivación.
- No repitas preguntas. No des feedback ni evalúes durante la entrevista.
- Llevas {hechas} de {total} preguntas principales. {fin}
{idioma}
Responde SOLO en JSON: {{"texto": "lo que dices", "tipo": "pregunta" | "repregunta" | "cierre"}}

PUESTO: {titulo} en {empresa}
{descripcion}

CV DEL CANDIDATO (para que las preguntas encajen con su perfil):
{cv}

CONVERSACIÓN HASTA AHORA:
{conversacion}
"""

PROMPT_INFORME = """Eres un coach de entrevistas de trabajo IT en Madrid. Evalúa esta entrevista con honestidad
y cariño: el candidato está en búsqueda activa y necesita mejorar, no que le hundan.
{idioma}
Para cada respuesta: nota 0-10, qué estuvo bien, qué mejorar (estructura situación→acción→resultado,
concreción, ir al grano) y una RESPUESTA MEJORADA en primera persona que use SOLO hechos de su CV.
PROHIBIDO inventar situaciones, días, clientes, averías, cifras o resultados que no estén en el CV:
cuando la pregunta pida un caso concreto, escribe la estructura con huecos, p. ej.
«En [empresa], [tu caso real: qué falló]. Lo primero que hice fue [acción]. El resultado fue [resultado].»
Responde SOLO en JSON:
{{"nota": 0-10, "resumen": "2-3 frases", "fuertes": ["..."], "mejorar": ["3 consejos concretos"],
"respuestas": [{{"pregunta": "...", "nota": 0-10, "bien": "...", "mejorar": "...", "mejorada": "..."}}]{extra}}}

CV DEL CANDIDATO:
{cv}

PUESTO: {titulo} en {empresa}

ENTREVISTA:
{conversacion}
"""


def _emit(evento, payload):
    try:
        socketio.emit(evento, payload)
    except Exception:
        pass

def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("sesiones", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

def _chat(prompt: str) -> dict:
    candidatura._omniroute_listo()
    try:
        return candidatura._chat_omniroute(prompt)
    except Exception as e:
        log(f"  ⚠ OmniRoute no respondió ({str(e)[:100]}); sigo con el modelo local, más flojo")
        return candidatura._chat_local(prompt)

def _conversacion(s: dict) -> str:
    return "\n".join(("ENTREVISTADOR: " if t["rol"] == "entrevistador" else "CANDIDATO: ") + t["texto"]
                     for t in s["turnos"]) or "(todavía no ha empezado)"

def _contexto(s: dict) -> dict:
    return {"titulo": s["titulo"], "empresa": s["empresa"], "descripcion": s["descripcion"][:4000],
            "cv": candidatura._cv(), "conversacion": _conversacion(s)}


# ─── Sesiones ──────────────────────────────────────────────────────────────────
def ofertas_disponibles() -> list:
    import ofertas
    items = ofertas._load()["items"].values()
    prio = {"entrevista": 0, "postulada": 1, "guardada": 2}
    elegibles = [i for i in items if i.get("estado") in prio or (i.get("eval") or {}).get("encaje", 0) >= 60
                 or i.get("relevancia", 0) >= 65]
    elegibles.sort(key=lambda i: (prio.get(i.get("estado"), 3), -i.get("relevancia", 0)))
    return [{"id": i["id"], "titulo": i["titulo"], "empresa": i.get("empresa", ""), "estado": i.get("estado")}
            for i in elegibles[:25]]

def listar() -> dict:
    d = _load()
    sesiones = sorted(d["sesiones"].values(), key=lambda s: s["creada"], reverse=True)
    resumen = [{k: s.get(k) for k in ("id", "titulo", "empresa", "idioma", "creada", "estado")}
               | {"nota": (s.get("informe") or {}).get("nota")} for s in sesiones]
    return {"sesiones": resumen, "ofertas": ofertas_disponibles(), "grabando": grabadora.grabando()}

def get(sid: str) -> dict:
    return _load()["sesiones"].get(sid) or {}

@_exclusivo
def nueva(oferta_id: str = "", idioma: str = "es", preguntas: int = 6) -> str:
    import ofertas
    idioma = "en" if idioma == "en" else "es"
    base = GENERICA
    if oferta_id:
        it = ofertas._load()["items"].get(oferta_id)
        if it:
            desc = it.get("descripcion") or ""
            if not desc and it.get("fuente") != "manual":
                try:
                    desc = ofertas._descripcion(it)
                except Exception:
                    desc = ""
            base = {"titulo": it["titulo"], "empresa": it.get("empresa") or "la empresa",
                    "descripcion": desc or it["titulo"]}
    sid = uuid.uuid4().hex[:10]
    s = {"id": sid, "oferta_id": oferta_id or None, **base, "idioma": idioma,
         "total": max(3, min(10, int(preguntas))), "turnos": [], "estado": "en_curso",
         "creada": datetime.datetime.now().isoformat(timespec="minutes")}
    d = _load()
    d["sesiones"][sid] = s
    _save(d)
    return sid

def _siguiente(sid: str):
    d = _load()
    s = d["sesiones"].get(sid)
    if not s or s["estado"] != "en_curso":
        return
    hechas = sum(1 for t in s["turnos"] if t["rol"] == "entrevistador" and t.get("tipo") == "pregunta")
    fin = ("Ya has hecho todas: despídete en una frase y di que le contactaréis (tipo «cierre»)."
           if hechas >= s["total"] else "")
    en = s["idioma"] == "en"
    r = _chat(PROMPT_TURNO.format(
        quien="a friendly IT hiring manager" if en else "un responsable técnico de selección",
        estilo=("Speak SIMPLE, CLEAR English (B1 level, short sentences): the candidate is Spanish and is "
                "practising English." if en else "Habla de tú, en español de España, cercano pero profesional."),
        hechas=hechas, total=s["total"], fin=fin,
        idioma="Write ONLY in English." if en else "Escribe SOLO en español.", **_contexto(s)))
    texto = str(r.get("texto", "")).strip() or ("Thank you, that's all for today." if en else "Gracias, eso es todo por hoy.")
    tipo = r.get("tipo") if r.get("tipo") in ("pregunta", "repregunta", "cierre") else "pregunta"
    if hechas >= s["total"]:
        tipo = "cierre"
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        s = d["sesiones"][sid]
        s["turnos"].append({"rol": "entrevistador", "texto": texto[:600], "tipo": tipo})
        _save(d)
    try:
        voz.sintetizar(texto[:600], s["idioma"])   # que el audio esté listo cuando llegue a la pantalla
    except Exception:
        pass
    _emit("entrevista_turno", {"id": sid})
    if tipo == "cierre":
        informe(sid)

def empezar(sid: str):
    _siguiente(sid)

def responder(sid: str, texto: str, segundos: int = 0, audio: str = ""):
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        s = d["sesiones"].get(sid)
        if not s or s["estado"] != "en_curso" or not texto.strip():
            return
        s["turnos"].append({"rol": "candidato", "texto": texto.strip()[:3000], "segundos": int(segundos),
                            "audio": os.path.basename(audio) if audio else ""})
        _save(d)
    _emit("entrevista_turno", {"id": sid})
    _siguiente(sid)

def informe(sid: str):
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        s = d["sesiones"].get(sid)
        if not s or not any(t["rol"] == "candidato" for t in s["turnos"]):
            return
        s["estado"] = "evaluando"
        _save(d)
    _emit("entrevista_turno", {"id": sid})
    log(f"🎤 Evaluando la entrevista de «{s['titulo'][:40]}»…")
    en = s["idioma"] == "en"
    r = _chat(PROMPT_INFORME.format(
        idioma=("Escribe el informe EN ESPAÑOL, pero las «mejorada» EN INGLÉS SENCILLO (B1). Añade «ingles»: "
                "lista de errores de inglés del candidato con su corrección." if en else "Escribe todo en español."),
        extra=', "ingles": [{"dijiste": "...", "mejor": "...", "por_que": "..."}]' if en else "",
        **_contexto(s)))
    def num(v):
        try:
            return max(0, min(10, round(float(v), 1)))
        except Exception:
            return None
    lista = lambda v, n=6: [str(x)[:300] for x in v][:n] if isinstance(v, list) else []
    inf = {"nota": num(r.get("nota")), "resumen": str(r.get("resumen", ""))[:800],
           "fuertes": lista(r.get("fuertes")), "mejorar": lista(r.get("mejorar")),
           "respuestas": [{"pregunta": str(x.get("pregunta", ""))[:400], "nota": num(x.get("nota")),
                           "bien": str(x.get("bien", ""))[:500], "mejorar": str(x.get("mejorar", ""))[:500],
                           "mejorada": str(x.get("mejorada", ""))[:1500]}
                          for x in r.get("respuestas", []) if isinstance(x, dict)][:12],
           "ingles": [{"dijiste": str(x.get("dijiste", ""))[:300], "mejor": str(x.get("mejor", ""))[:300],
                       "por_que": str(x.get("por_que", ""))[:300]}
                      for x in r.get("ingles", []) if isinstance(x, dict)][:15] if en else []}
    # el mismo revisor de las candidaturas: frases de las «mejoradas» que no respalda el CV
    try:
        prep = {"perfil": "", "carta": "", "encaje": [], "preguntas_en": [],
                "preguntas": [{"pregunta": x["pregunta"], "respuesta": x["mejorada"]} for x in inf["respuestas"]]}
        inf["avisos"] = candidatura._auditar(prep, candidatura._cv(), candidatura._logros())
    except Exception:
        inf["avisos"] = []
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        s = d["sesiones"][sid]
        s["informe"], s["estado"] = inf, "terminada"
        habladas = [t for t in s["turnos"] if t["rol"] == "candidato"]
        inf["minutos_hablando"] = round(sum(t.get("segundos", 0) for t in habladas) / 60, 1)
        _save(d)
    log(f"🎤 Entrevista evaluada: {inf['nota']}/10")
    _emit("entrevista_turno", {"id": sid})

@_exclusivo
def borrar(sid: str) -> bool:
    d = _load()
    if d["sesiones"].pop(sid, None) is None:
        return False
    _save(d)
    return True


# ─── Voz ───────────────────────────────────────────────────────────────────────
def grabar(sid: str) -> bool:
    if not get(sid):
        return False
    n = len(get(sid)["turnos"])
    grabadora.empezar(os.path.join(GRABACIONES, f"{sid}-{n:02d}.wav"))
    return True

def parar_y_transcribir(sid: str) -> dict:
    ruta, segundos = grabadora.parar()
    if not ruta or not os.path.isfile(ruta):
        return {"error": "No se grabó nada"}
    if segundos < 1:
        return {"error": "Grabación demasiado corta"}
    s = get(sid)
    if voz.nivel(ruta) < UMBRAL_SILENCIO:
        return {"error": "No te he oído: la grabación está casi en silencio. ¿Están conectados los cascos? "
                         "(el micro es el de los cascos). Vuelve a grabar o escribe la respuesta.",
                "audio": os.path.basename(ruta), "segundos": segundos}
    try:
        texto = voz.transcribir(ruta, s.get("idioma", "es"))
    except Exception as e:
        return {"error": f"No pude pasar tu voz a texto ({str(e)[:120]}). Escríbela en el cuadro.",
                "audio": os.path.basename(ruta), "segundos": segundos}
    return {"texto": texto, "segundos": segundos, "audio": os.path.basename(ruta)}

def audio_turno(sid: str, n: int) -> str:
    s = get(sid)
    try:
        t = s["turnos"][n]
    except (KeyError, IndexError, TypeError):
        return ""
    if t["rol"] == "entrevistador":
        return voz.sintetizar(t["texto"], s["idioma"])
    ruta = os.path.join(GRABACIONES, t.get("audio") or "")
    return ruta if t.get("audio") and re.fullmatch(r"[0-9a-f]{10}-\d{2}\.wav", t["audio"]) and os.path.isfile(ruta) else ""

def limpiar_grabaciones():
    limite = time.time() - 30 * 86400
    if os.path.isdir(GRABACIONES):
        for f in os.listdir(GRABACIONES):
            p = os.path.join(GRABACIONES, f)
            if os.path.getmtime(p) < limite:
                os.remove(p)
