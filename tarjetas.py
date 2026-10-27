"""
Centro de Control PRO — tarjetas.py
De una captura (o de un texto) a tarjetas de repaso.

Pegas o arrastras una captura de NetAcad, MS Learn o tus apuntes; un modelo con
visión (Claude vía OmniRoute; si falla, «tutor-estudio» en Ollama, local) lee
lo que hay y propone 3-6 tarjetas pregunta/respuesta en español, con los
términos técnicos en su forma original. Tú las revisas y guardas las que
quieras. Repaso espaciado por cajas como el de Inglés (1, 2, 4, 8, 16 días).

La captura se guarda en pequeño junto a la tarjeta para ver de dónde salió.
Datos en tarjetas_data.json e imágenes en ~/.local/share/mipanelcontrol/tarjetas.
"""

import base64
import datetime
import hashlib
import json
import os
import re
import threading
import urllib.request
import uuid

import candidatura
from rag import _json_ollama
import almacen

DATA_FILE  = os.path.expanduser(os.environ.get("TARJETAS_DATA", "~/MiPanelControl/tarjetas_data.json"))
IMG_DIR    = os.path.expanduser("~/.local/share/mipanelcontrol/tarjetas")
INTERVALOS = [0, 1, 2, 4, 8, 16]
NUEVAS_DIA = 10
MODELO_LOCAL = os.environ.get("MODELO_VISION_LOCAL", "tutor-estudio")
_lock      = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)

PROMPT = """Eres un profesor que prepara a un técnico de sistemas para certificaciones (CCNA, LPIC, AZ-104).
{fuente}
Crea entre 3 y 6 tarjetas de repaso SOLO con lo que aparece en el material (no añadas datos de fuera).
Preguntas concretas que se puedan responder en una o dos frases: definiciones, comandos y su efecto,
valores por defecto, diferencias entre conceptos, pasos de un procedimiento. Pregunta en español; deja los
comandos y términos técnicos tal cual (en inglés si así aparecen).
Responde SOLO en JSON:
{{"materia": "CCNA | LPIC | AZ-104 | Otra", "tarjetas": [{{"pregunta": "...", "respuesta": "...", "explicacion": "una frase de contexto (opcional)"}}]}}
"""


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("tarjetas", {})
    d.setdefault("historial", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

def _hoy() -> str:
    return datetime.date.today().isoformat()


# ─── Generar ───────────────────────────────────────────────────────────────────
def _con_omniroute(texto: str, imagen_b64: str = "", mime: str = "image/png") -> dict:
    clave = os.environ.get("OMNIROUTE_API_KEY", "")
    contenido = [{"type": "text", "text": texto}]
    if imagen_b64:
        contenido.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{imagen_b64}"}})
    candidatura._omniroute_listo()
    pet = urllib.request.Request(candidatura.OMNIROUTE_URL, method="POST", data=json.dumps({
        "model": candidatura.OMNIROUTE_MODELO, "temperature": 0.2,
        "messages": [{"role": "user", "content": contenido}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {clave}"})
    with urllib.request.urlopen(pet, timeout=180) as r:
        d = json.load(r)
    if d.get("error"):
        raise RuntimeError(str(d["error"])[:200])
    return candidatura._json_de(d["choices"][0]["message"]["content"])

def _con_ollama(texto: str, imagen_b64: str = "") -> dict:
    from rag import _ollama_post
    msg = {"role": "user", "content": texto}
    if imagen_b64:
        msg["images"] = [imagen_b64]
    r = _ollama_post("/api/chat", {"model": MODELO_LOCAL, "format": "json", "stream": False,
                                   "messages": [msg]}, timeout=400)
    return _json_ollama(r)

def proponer(imagen_b64: str = "", mime: str = "image/png", texto: str = "") -> dict:
    """Devuelve tarjetas PROPUESTAS (no se guardan hasta que el usuario las acepta)."""
    if imagen_b64:
        try:
            crudo = base64.b64decode(imagen_b64, validate=True)
        except Exception:
            return {"error": "La imagen no es válida"}
        if len(crudo) > 8 * 1024 * 1024:
            return {"error": "La imagen pasa de 8 MB"}
        if not (crudo[:8] == b"\x89PNG\r\n\x1a\n" or crudo[:3] == b"\xff\xd8\xff" or crudo[8:12] == b"WEBP"):
            return {"error": "Solo PNG, JPG o WEBP"}
        fuente = "Material: la CAPTURA adjunta."
    elif texto.strip():
        fuente = "Material:\n" + texto.strip()[:6000]
    else:
        return {"error": "Pega una captura o un texto"}
    prompt = PROMPT.format(fuente=fuente)
    try:
        r, modelo = _con_omniroute(prompt, imagen_b64, mime), candidatura.OMNIROUTE_MODELO
    except Exception as e:
        try:
            r, modelo = _con_ollama(prompt, imagen_b64), MODELO_LOCAL
        except Exception:
            return {"error": f"No pude leer el material con ningún modelo ({str(e)[:100]})"}
    tarjetas = [{"pregunta": str(t.get("pregunta", "")).strip()[:300], "respuesta": str(t.get("respuesta", "")).strip()[:600],
                 "explicacion": str(t.get("explicacion", "") or "").strip()[:300]}
                for t in r.get("tarjetas", []) if isinstance(t, dict) and t.get("pregunta") and t.get("respuesta")][:8]
    imagen = ""
    if imagen_b64:   # se guarda la captura para poder verla desde la tarjeta
        os.makedirs(IMG_DIR, exist_ok=True)
        imagen = hashlib.sha1(crudo).hexdigest()[:16] + {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
        with open(os.path.join(IMG_DIR, imagen), "wb") as f:
            f.write(crudo)
    return {"tarjetas": tarjetas, "materia": str(r.get("materia", "Otra"))[:20], "modelo": modelo, "imagen": imagen}

@_exclusivo
def guardar(tarjetas: list, materia: str = "", imagen: str = "") -> int:
    if imagen and not re.fullmatch(r"[0-9a-f]{16}\.(png|jpg|webp)", imagen):
        imagen = ""
    d = _load()
    n = 0
    for t in tarjetas[:10]:
        p, r = str(t.get("pregunta", "")).strip(), str(t.get("respuesta", "")).strip()
        if not p or not r:
            continue
        tid = uuid.uuid4().hex[:10]
        d["tarjetas"][tid] = {"id": tid, "pregunta": p[:300], "respuesta": r[:600],
                              "explicacion": str(t.get("explicacion", "")).strip()[:300], "materia": materia[:20] or "Otra",
                              "imagen": imagen, "caja": 0, "proxima": None, "creada": _hoy()}
        n += 1
    _save(d)
    return n


# ─── Repaso ────────────────────────────────────────────────────────────────────
def get_data() -> dict:
    d = _load()
    hoy = _hoy()
    ts = list(d["tarjetas"].values())
    vencidas = sorted((t for t in ts if t["caja"] > 0 and t["proxima"] and t["proxima"] <= hoy), key=lambda t: t["proxima"])
    estrenos = sum(1 for t in ts if t.get("estreno") == hoy)
    nuevas = sorted((t for t in ts if t["caja"] == 0), key=lambda t: t["creada"])[:max(0, NUEVAS_DIA - estrenos)]
    materias = {}
    for t in ts:
        materias[t["materia"]] = materias.get(t["materia"], 0) + 1
    return {"cola": (vencidas + nuevas)[:30], "total": len(ts), "aprendidas": sum(1 for t in ts if t["caja"] >= 4),
            "hechas_hoy": d["historial"].get(hoy, 0), "materias": materias,
            "todas": sorted(ts, key=lambda t: t["creada"], reverse=True)[:200]}

@_exclusivo
def repasar(tid: str, acierto: bool) -> bool:
    d = _load()
    t = d["tarjetas"].get(tid)
    if not t:
        return False
    if t["caja"] == 0:
        t["estreno"] = _hoy()
    t["caja"] = min(len(INTERVALOS) - 1, t["caja"] + 1) if acierto else 1
    t["proxima"] = (datetime.date.today() + datetime.timedelta(days=INTERVALOS[t["caja"]])).isoformat()
    d["historial"][_hoy()] = d["historial"].get(_hoy(), 0) + 1
    _save(d)
    return True

@_exclusivo
def borrar(tid: str) -> bool:
    d = _load()
    if d["tarjetas"].pop(tid, None) is None:
        return False
    _save(d)
    return True

def ruta_imagen(nombre: str) -> str:
    ruta = os.path.join(IMG_DIR, nombre)
    return ruta if re.fullmatch(r"[0-9a-f]{16}\.(png|jpg|webp)", nombre) and os.path.isfile(ruta) else ""
