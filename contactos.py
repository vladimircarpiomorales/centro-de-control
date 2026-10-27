"""
Centro de Control PRO — contactos.py
Agenda de contactos de la búsqueda de empleo (reclutadores, gente de empresas,
compañeros) con seguimiento y borradores de mensaje.

Cada contacto tiene un estado (por contactar → contactado → respondió → en
conversación / frío), un historial y una fecha de «próximo paso»: cuando llega,
aparece en Hoy. «✍ Borrador» pide a Claude (vía OmniRoute, como las
candidaturas) un mensaje corto con tus datos reales; la nota de conexión de
LinkedIn se corta a 300 caracteres, que es su límite.
Datos en contactos_data.json (fuera de git).
"""

import datetime
import json
import os
import threading
import uuid

import candidatura
import almacen

DATA_FILE = os.path.expanduser(os.environ.get("CONTACTOS_DATA", "~/MiPanelControl/contactos_data.json"))
ESTADOS   = ["por_contactar", "contactado", "respondio", "conversacion", "frio"]
TIPOS_MSG = {
    "conectar": "nota para la invitación de conexión en LinkedIn: MÁXIMO 280 caracteres, sin saludo largo, "
                "di quién eres y por qué conectas con esta persona en concreto",
    "seguimiento": "mensaje de seguimiento de una candidatura enviada hace días: educado, breve (60-90 palabras), "
                   "recuerda el puesto y aporta UN dato de tu experiencia que encaje",
    "gracias": "agradecimiento tras una entrevista: breve (60-90 palabras), menciona algo concreto de la conversación "
               "si las notas lo dicen, reafirma tu interés",
    "charla": "petición de una charla informativa de 15 minutos sobre su empresa o su puesto: breve, sin pedir trabajo directamente",
    "referencia": "petición de referencia o recomendación para una oferta concreta de su empresa: breve y concreto",
}
_lock = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("contactos", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

def _hoy() -> str:
    return datetime.date.today().isoformat()

@_exclusivo
def guardar(c: dict) -> str:
    d = _load()
    cid = str(c.get("id") or "")
    previo = d["contactos"].get(cid, {}) if cid in d["contactos"] else {}
    cid = cid if previo else uuid.uuid4().hex[:10]
    proximo = str(c.get("proximo") or "")
    if proximo:
        datetime.date.fromisoformat(proximo)
    d["contactos"][cid] = {
        "id": cid, "nombre": str(c.get("nombre", "")).strip()[:80] or "Sin nombre",
        "empresa": str(c.get("empresa", "")).strip()[:80], "rol": str(c.get("rol", "")).strip()[:80],
        "enlace": str(c.get("enlace", "")).strip()[:300], "notas": str(c.get("notas", "")).strip()[:1500],
        "estado": c.get("estado") if c.get("estado") in ESTADOS else previo.get("estado", "por_contactar"),
        "proximo": proximo, "proximo_que": str(c.get("proximo_que", "")).strip()[:120],
        "ultimo_contacto": previo.get("ultimo_contacto"), "historial": previo.get("historial", []),
        "creado": previo.get("creado", _hoy()),
    }
    _save(d)
    return cid

@_exclusivo
def borrar(cid: str) -> bool:
    d = _load()
    if d["contactos"].pop(cid, None) is None:
        return False
    _save(d)
    return True

@_exclusivo
def anotar(cid: str, texto: str, estado: str = "", dias_siguiente: int = 7) -> bool:
    """Registra un contacto hecho hoy y programa el siguiente paso."""
    d = _load()
    c = d["contactos"].get(cid)
    if not c:
        return False
    c["historial"].insert(0, {"fecha": _hoy(), "texto": texto.strip()[:300] or "Contacto"})
    c["historial"] = c["historial"][:30]
    c["ultimo_contacto"] = _hoy()
    if estado in ESTADOS:
        c["estado"] = estado
    elif c["estado"] == "por_contactar":
        c["estado"] = "contactado"
    if dias_siguiente and c["estado"] != "frio":
        c["proximo"] = (datetime.date.today() + datetime.timedelta(days=int(dias_siguiente))).isoformat()
        c["proximo_que"] = c.get("proximo_que") or "Volver a escribir si no responde"
    _save(d)
    return True

def get_data() -> dict:
    hoy = _hoy()
    cs = list(_load()["contactos"].values())
    for c in cs:
        c["toca"] = bool(c.get("proximo")) and c["proximo"] <= hoy and c["estado"] != "frio"
    orden = {e: i for i, e in enumerate(ESTADOS)}
    cs.sort(key=lambda c: (not c["toca"], c.get("proximo") or "9999", orden.get(c["estado"], 9)))
    return {"contactos": cs, "estados": ESTADOS, "tipos": list(TIPOS_MSG), "pendientes": sum(c["toca"] for c in cs)}


PROMPT = """Escribe un mensaje de búsqueda de empleo de parte del candidato. Tipo: {tipo}.
Idioma: {idioma}. Tono natural y humano, nada de frases de plantilla ni adulación.
Usa SOLO hechos del CV; no inventes experiencia, cifras ni que conoces a la persona si las notas no lo dicen.
{reglas}
Responde SOLO en JSON: {{"asunto": "asunto si es email (o vacío)", "mensaje": "el texto listo para enviar"}}

DESTINATARIO: {nombre} — {rol} en {empresa}
NOTAS SOBRE ESTA PERSONA / CONTEXTO: {notas}
{oferta}
CV DEL CANDIDATO:
{cv}
"""

def borrador(cid: str, tipo: str, idioma: str = "es", oferta_id: str = "") -> dict:
    c = _load()["contactos"].get(cid)
    if not c or tipo not in TIPOS_MSG:
        return {"error": "Contacto o tipo de mensaje no válido"}
    oferta = ""
    if oferta_id:
        import ofertas
        it = ofertas._load()["items"].get(oferta_id)
        if it:
            oferta = f"OFERTA RELACIONADA: {it['titulo']} en {it.get('empresa', '')}\n{(it.get('descripcion') or '')[:1500]}\n"
    candidatura._omniroute_listo()
    prompt = PROMPT.format(tipo=TIPOS_MSG[tipo], idioma="inglés sencillo y correcto" if idioma == "en" else "español de España",
                           reglas=candidatura.REGLAS,
                           nombre=c["nombre"], rol=c.get("rol") or "—", empresa=c.get("empresa") or "—",
                           notas=c.get("notas") or "(ninguna)", oferta=oferta, cv=candidatura._cv()[:6000])
    try:
        r = candidatura._chat_omniroute(prompt)
    except Exception as e:
        try:
            r = candidatura._chat_local(prompt)
        except Exception:
            return {"error": f"No pude hablar con ningún modelo ({str(e)[:100]})"}
    mensaje = str(r.get("mensaje", "")).strip()
    if tipo == "conectar" and len(mensaje) > 300:
        mensaje = mensaje[:297].rsplit(" ", 1)[0] + "…"
    # el mismo revisor de las candidaturas (etapas cerradas en presente, certificaciones…)
    avisos = candidatura._revisar({"perfil": mensaje, "carta": "", "encaje": [], "huecos": [], "preguntas": [],
                                   "preguntas_en": []}, candidatura._cv(), oferta, solo_precisas=True)
    return {"asunto": str(r.get("asunto", "")).strip()[:150], "mensaje": mensaje, "caracteres": len(mensaje),
            "avisos": avisos}
