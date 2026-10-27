"""
Centro de Control PRO — carrera_cv.py
Puente entre los logros/hitos del plan de carrera y el CV en Reactive Resume.

Flujo: el usuario pulsa "→ CV" en un logro → el modelo local (Ollama) decide si
merece ir al CV, en qué sección y con qué redacción → se muestra la propuesta →
si el usuario la aprueba, se aplica vía JSON Patch (RFC 6902) contra la API
OpenAPI de Reactive Resume (PATCH /api/openapi/resumes/{id}).

Config en .env:
  RESUME_URL      (default http://localhost:3004)
  RESUME_API_KEY  (crear en Reactive Resume → Settings → API Keys)
  RESUME_ID       (opcional; si falta se usa el primer CV de la cuenta)
"""

import perfil as _perfilmod
_P = _perfilmod.get()
import json
import os
import time
import urllib.error
import urllib.request
import uuid

from extensions import socketio
from status import log
from rag import _ollama_post, _json_ollama

RESUME_URL = os.environ.get("RESUME_URL", "http://127.0.0.1:3004").rstrip("/")
MODELO_DEFAULT = "llama3.1"

# Secciones donde sabemos insertar items automáticamente, con su plantilla base.
# Los campos en MODELO_CAMPOS son los que el modelo debe redactar.
PLANTILLAS = {
    "certifications": {"id": "", "hidden": False, "title": "", "issuer": "", "date": "",
                       "website": {"url": "", "label": "", "inlineLink": False}, "description": ""},
    "projects":       {"id": "", "hidden": False, "name": "", "period": "",
                       "website": {"url": "", "label": "", "inlineLink": False}, "description": ""},
    "awards":         {"id": "", "hidden": False, "title": "", "awarder": "", "date": "",
                       "website": {"url": "", "label": "", "inlineLink": False}, "description": ""},
    "education":      {"id": "", "hidden": False, "school": "", "degree": "", "area": "", "grade": "",
                       "location": "", "period": "",
                       "website": {"url": "", "label": "", "inlineLink": False}, "description": ""},
    "volunteer":      {"id": "", "hidden": False, "organization": "", "location": "", "period": "",
                       "website": {"url": "", "label": "", "inlineLink": False}, "description": ""},
    "skills":         {"id": "", "hidden": False, "icon": "", "iconColor": "", "name": "",
                       "proficiency": "", "level": 0, "keywords": []},
}

MODELO_CAMPOS = {
    "certifications": "title (nombre de la certificación), issuer (entidad emisora), date (año o fecha)",
    "projects":       "name (nombre del proyecto), period (periodo), description (1-2 frases en HTML <p>...</p>)",
    "awards":         "title (nombre del premio/reconocimiento), awarder (quién lo otorga), date (año)",
    "education":      "school (institución), degree (título obtenido), area (especialidad), period (periodo)",
    "volunteer":      "organization (organización y rol), location (ciudad), period (periodo)",
    "skills":         "name (nombre de la competencia), keywords (lista de palabras clave)",
    "experience":     "texto del bullet a añadir en una experiencia existente",
}

# Campo obligatorio (min 1 carácter en el esquema de Reactive Resume) por sección
CAMPO_REQUERIDO = {"certifications": "title", "projects": "name", "awards": "title",
                   "education": "school", "volunteer": "organization", "skills": "name"}


# ─── Cliente API Reactive Resume ────────────────────────────────────────────────
def _api(method: str, path: str, payload=None, timeout: int = 30):
    api_key = os.environ.get("RESUME_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Falta RESUME_API_KEY en el .env del panel")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{RESUME_URL}/api/openapi{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Reactive Resume respondió {e.code}: {cuerpo}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"No llego a Reactive Resume en {RESUME_URL} — ¿está encendido? ({e.reason})") from e


def _listar_resumes() -> list:
    r = _api("GET", "/resumes")
    items = r if isinstance(r, list) else r.get("items", r.get("data", []))
    return [{"id": x["id"], "name": x.get("name", x.get("title", "?")), "slug": x.get("slug", "")} for x in items]


def _resume_objetivo() -> dict:
    """El CV a modificar: RESUME_ID del .env, o el primero de la cuenta."""
    quiero = os.environ.get("RESUME_ID", "").strip()
    resumes = _listar_resumes()
    if not resumes:
        raise RuntimeError("No hay ningún CV en Reactive Resume — importa uno primero")
    if quiero:
        for r in resumes:
            if r["id"] == quiero or r["slug"] == quiero:
                return r
        raise RuntimeError(f"RESUME_ID={quiero} no existe en Reactive Resume")
    return resumes[0]


def estado() -> dict:
    """Para el UI: ¿está configurado el puente? ¿qué CV se tocaría?"""
    if not os.environ.get("RESUME_API_KEY", "").strip():
        return {"ok": False, "motivo": "sin_api_key"}
    try:
        r = _resume_objetivo()
        return {"ok": True, "resume": r}
    except RuntimeError as e:
        return {"ok": False, "motivo": "error", "detalle": str(e)}


# ─── Propuesta con el modelo local ──────────────────────────────────────────────
def _prompt_propuesta(texto: str, data: dict) -> str:
    secciones_actuales = []
    for sec in PLANTILLAS:
        items = data.get("sections", {}).get(sec, {}).get("items", [])
        nombres = [i.get("title") or i.get("name") or i.get("organization") or i.get("school") or "" for i in items]
        secciones_actuales.append(f"- {sec}: {len(items)} items ({'; '.join(n for n in nombres if n)[:200]})")
    campos = "\n".join(f"- {s}: {c}" for s, c in MODELO_CAMPOS.items())
    return (
        f"Eres el asistente de CV de {_P.get('nombre', 'la persona usuaria')} ({_P.get('cv_asistente', 'buscando empleo')}). "
        "Evalúa si el siguiente logro merece entrar en su CV profesional y dónde.\n\n"
        f"LOGRO: {texto}\n\n"
        f"SECCIONES DEL CV Y CONTENIDO ACTUAL:\n{chr(10).join(secciones_actuales)}\n\n"
        "CRITERIO ESTRICTO: al CV solo entra lo que impresiona a un reclutador técnico "
        "(certificaciones, proyectos con sustancia, premios, formación). Logros personales/motivacionales "
        "(rachas de estudio, tareas pequeñas, configuraciones domésticas menores) NO van. "
        "Si ya existe un item equivalente en la sección, responde que no (duplicado).\n\n"
        f"CAMPOS A REDACTAR SEGÚN SECCIÓN:\n{campos}\n\n"
        "Responde SOLO con JSON válido, sin texto extra, con esta estructura exacta:\n"
        '{"va_al_cv": true/false, "seccion": "certifications|projects|awards|education|volunteer|skills|experience|ninguna", '
        '"razon": "explicación breve en español", "campos": {objeto con los campos de la sección elegida, en español}}'
    )


def proponer(texto: str, modelo: str = MODELO_DEFAULT):
    """Corre en background: pide propuesta al modelo y la emite por socket."""
    try:
        st = estado()
        if not st["ok"]:
            raise RuntimeError("Configura primero la conexión con Reactive Resume"
                               if st["motivo"] == "sin_api_key" else st.get("detalle", "error"))
        resume = st["resume"]
        data = _api("GET", f"/resumes/{resume['id']}").get("data", {})

        log(f"📄 Evaluando si el logro va al CV ({modelo})...")
        r = _ollama_post("/api/chat", {
            "model": modelo, "format": "json", "stream": False,
            "messages": [{"role": "user", "content": _prompt_propuesta(texto, data)}],
        }, timeout=420)
        prop = _json_ollama(r)
    except Exception as e:
        log(f"⚠ Propuesta CV: {e}")
        socketio.emit("carrera_cv", {"tipo": "error", "texto": str(e)})
        return

    seccion = prop.get("seccion", "ninguna")
    campos  = prop.get("campos") or {}
    va      = bool(prop.get("va_al_cv")) and seccion in MODELO_CAMPOS

    item, aplicable = None, False
    if va and seccion in PLANTILLAS:
        item = json.loads(json.dumps(PLANTILLAS[seccion]))          # copia profunda
        for k, v in campos.items():
            if k in item and not isinstance(item[k], dict):
                item[k] = [str(x) for x in v] if isinstance(v, list) else str(v)
        item["id"] = f"panel-{uuid.uuid4().hex[:12]}"
        aplicable = bool(str(item.get(CAMPO_REQUERIDO[seccion], "")).strip())

    socketio.emit("carrera_cv", {
        "tipo": "propuesta",
        "logro": texto,
        "va_al_cv": va,
        "seccion": seccion,
        "razon": prop.get("razon", ""),
        "item": item,
        "aplicable": aplicable,                       # False → solo sugerencia (p.ej. bullet de experiencia)
        "sugerencia": campos if (va and not aplicable) else None,
        "resume": resume,
    })
    log("📄 Propuesta de CV lista — revísala en el panel")


def aplicar(seccion: str, item: dict) -> dict:
    """Aplica la propuesta aprobada: añade el item al final de la sección del CV."""
    if seccion not in PLANTILLAS or not isinstance(item, dict):
        raise RuntimeError("Propuesta no aplicable automáticamente")
    resume = _resume_objetivo()
    _api("PATCH", f"/resumes/{resume['id']}", {
        "operations": [{"op": "add", "path": f"/sections/{seccion}/items/-", "value": item}],
    })
    etiqueta = item.get(CAMPO_REQUERIDO[seccion], "")
    log(f"✅ CV actualizado: «{etiqueta}» añadido a {seccion} en '{resume['name']}'")
    return {"ok": True, "resume": resume, "seccion": seccion, "etiqueta": etiqueta}
