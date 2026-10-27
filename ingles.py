"""
Centro de Control PRO — ingles.py
Inglés técnico sacado de las ofertas de empleo que de verdad te interesan.

El inglés fue lo que más pesó en el AZ-104 y es lo que piden las ofertas. En vez
de un curso genérico, el vocabulario sale de:
  1. Una semilla de ~50 expresiones que se repiten en anuncios IT (funciona sin IA).
  2. Las ofertas mejor puntuadas: se lee la descripción y Ollama extrae las
     expresiones en inglés que aparecen LITERALMENTE en el texto (se comprueba
     que estén; lo que el modelo invente se descarta), con la frase de la oferta.

Repaso espaciado por cajas (Leitner): acertar sube de caja y espacia el siguiente
repaso (1, 2, 4, 8, 16 días); fallar la devuelve a la caja 1. Como máximo
NUEVAS_DIA tarjetas nuevas al día, para que el repaso no se haga una montaña.
Persistencia en ingles_data.json.
"""

import datetime
import hashlib
import json
import os
import re
import threading
import time

from extensions import socketio
from status import log
from rag import _ollama_post, _json_ollama
import almacen

DATA_FILE   = os.path.expanduser(os.environ.get("INGLES_DATA", "~/MiPanelControl/ingles_data.json"))
INTERVALOS  = [0, 1, 2, 4, 8, 16]   # días hasta el siguiente repaso según la caja
NUEVAS_DIA  = 8
REPASO_MAX  = 20
MODELO      = "qwen3.5:4b"
_lock       = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)
_extrayendo = threading.Lock()

# Voz: Piper (neuronal, local). La voz del navegador del panel sonaba robótica y
# con acento español: WebKitGTK no tiene motor de voz decente sin speech-dispatcher.
VOZ_DIR    = os.path.expanduser(os.environ.get("PIPER_DIR", "~/.local/share/piper"))
VOZ        = os.environ.get("INGLES_VOZ", "en_US-lessac-medium")   # o en_GB-alba-medium
AUDIO_DIR  = os.path.expanduser("~/.cache/mipanelcontrol/ingles-audio")
_voz       = {"modelo": None}
_voz_lock  = threading.Lock()

# en, es, ejemplo, nota — expresiones que salen una y otra vez en ofertas de sistemas/redes/cloud
SEMILLA = [
    ("troubleshooting", "diagnóstico y resolución de incidencias", "Strong troubleshooting skills in Windows and Linux environments.", ""),
    ("on-call", "guardias (disponible fuera de horario)", "Participation in an on-call rotation is required.", "on-call rotation = turno de guardias"),
    ("hands-on experience", "experiencia práctica, de haberlo hecho", "Hands-on experience with VMware vSphere.", ""),
    ("stakeholders", "partes interesadas (jefes, clientes, otros equipos)", "Communicate clearly with technical and non-technical stakeholders.", ""),
    ("rollout", "despliegue / implantación progresiva", "Support the rollout of Windows 11 across the company.", ""),
    ("ticketing system", "herramienta de tickets/incidencias", "Manage requests through our ticketing system (ServiceNow, Jira).", ""),
    ("SLA", "acuerdo de nivel de servicio (tiempos comprometidos)", "Resolve incidents within the agreed SLA.", "Service Level Agreement"),
    ("root cause analysis", "análisis de la causa raíz", "Perform root cause analysis after major incidents.", "a veces RCA"),
    ("uptime", "tiempo en servicio / disponibilidad", "Ensure 99.9% uptime of critical systems.", ""),
    ("patching", "aplicación de parches/actualizaciones", "Regular patching of servers and network devices.", ""),
    ("to maintain", "mantener", "Install, configure and maintain Linux servers.", ""),
    ("to provision", "aprovisionar (crear y preparar recursos)", "Provision virtual machines in Azure.", ""),
    ("to deploy", "desplegar / poner en marcha", "Deploy and manage infrastructure as code.", ""),
    ("to monitor", "supervisar / vigilar", "Monitor network performance and availability.", ""),
    ("to escalate", "escalar (pasar a un nivel superior)", "Escalate complex issues to second-level support.", ""),
    ("first-line support", "soporte de primer nivel (N1)", "Provide first-line support to end users.", "second-line = N2, third-line = N3"),
    ("end users", "usuarios finales", "Assist end users with hardware and software issues.", ""),
    ("requirements", "requisitos", "Requirements: 2+ years in a similar role.", ""),
    ("nice to have", "valorable (no obligatorio)", "Nice to have: CCNA or AZ-104 certification.", "lo opuesto a must have"),
    ("must have", "imprescindible", "Must have: fluent Spanish and basic English.", ""),
    ("proficiency", "dominio / competencia", "Proficiency in PowerShell scripting.", ""),
    ("fluent", "con fluidez", "Fluent in Spanish; English is a plus.", ""),
    ("is a plus", "es un plus / se valora", "Experience with Terraform is a plus.", ""),
    ("background in", "formación o experiencia previa en", "Background in networking or system administration.", ""),
    ("track record", "historial demostrable de resultados", "Proven track record of managing IT infrastructure.", ""),
    ("to be in charge of", "estar a cargo de", "You will be in charge of the backup infrastructure.", ""),
    ("duties", "funciones / tareas del puesto", "Main duties include user support and server maintenance.", "también responsibilities"),
    ("shift", "turno", "Rotating shifts, including weekends.", ""),
    ("hybrid", "híbrido (parte oficina, parte casa)", "Hybrid model: 3 days in the office, 2 remote.", ""),
    ("remote-first", "remoto por defecto", "We are a remote-first company.", ""),
    ("salary range", "banda salarial", "Salary range: 28,000–34,000 € gross per year.", "gross = bruto, net = neto"),
    ("benefits", "beneficios sociales", "Benefits: health insurance, training budget, flexible hours.", ""),
    ("onboarding", "incorporación y formación inicial", "You will receive a full onboarding plan.", ""),
    ("to apply", "postular / presentar candidatura", "Apply now with your CV in English.", "application = candidatura"),
    ("cover letter", "carta de presentación", "Please include a short cover letter.", ""),
    ("deadline", "fecha límite", "Application deadline: 30 November.", ""),
    ("workload", "carga de trabajo", "Ability to manage a varied workload.", ""),
    ("fast-paced environment", "entorno dinámico, con mucho ritmo", "You will work in a fast-paced environment.", ""),
    ("self-starter", "persona proactiva, que empieza sola", "We are looking for a self-starter.", ""),
    ("team player", "persona que trabaja bien en equipo", "Team player with good communication skills.", ""),
    ("to troubleshoot", "diagnosticar y arreglar", "Troubleshoot connectivity issues (DNS, DHCP, VPN).", ""),
    ("outage", "caída / corte del servicio", "Respond quickly to outages.", ""),
    ("downtime", "tiempo de inactividad", "Plan maintenance to minimise downtime.", ""),
    ("backup and recovery", "copias de seguridad y recuperación", "Manage backup and recovery with Veeam.", ""),
    ("disaster recovery", "recuperación ante desastres", "Maintain the disaster recovery plan.", "DR"),
    ("compliance", "cumplimiento normativo", "Ensure compliance with security policies (ISO 27001).", ""),
    ("hardening", "bastionado (endurecer la seguridad)", "Server hardening and vulnerability management.", ""),
    ("least privilege", "mínimo privilegio", "Apply the principle of least privilege.", ""),
    ("scripting", "programación de scripts", "Scripting skills in Bash or PowerShell.", ""),
    ("documentation", "documentación", "Keep technical documentation up to date.", "up to date = al día"),
    ("knowledge base", "base de conocimiento", "Contribute articles to the knowledge base.", ""),
    ("handover", "traspaso de trabajo / relevo", "Write a clear handover at the end of each shift.", ""),
]

PROMPT_ES = """Eres profesor de inglés para un técnico de sistemas hispanohablante con inglés básico
que se prepara entrevistas en inglés. Esta OFERTA DE EMPLEO está en español. Elige hasta 8
expresiones de 2 a 6 palabras sobre TAREAS, RESPONSABILIDADES o REQUISITOS que tendría que
saber decir en inglés al hablar de su trabajo. Copia cada expresión EXACTAMENTE como aparece
en el texto (mismas palabras y acentos). NO elijas el título del puesto ni nombres de productos.
Usa el inglés real de IT: guardias = on-call, incidencias = incidents, peticiones = requests,
puntual(es) = occasional, parcheado = patching, monitorización = monitoring, copias de
seguridad = backups, proveedores = vendors, bastionado = hardening, despliegue = deployment.
Responde SOLO en JSON:
{"terminos": [{"es": "expresión copiada del texto", "en": "cómo lo diría en inglés un profesional IT, natural y corto"}]}

OFERTA:
"""

PROMPT_EXTRAER = """Eres profesor de inglés para un técnico de sistemas hispanohablante con inglés básico.
Del texto de esta OFERTA DE EMPLEO, extrae hasta 10 expresiones EN INGLÉS que aparezcan
literalmente en el texto y que le sirvan para entender anuncios y entrevistas de IT
(verbos de trabajo, expresiones de requisitos, conceptos de operación). NO incluyas:
nombres de productos o marcas (Azure, Cisco, Windows…), siglas sueltas, ni palabras en español.
Responde SOLO en JSON con esta forma:
{"terminos": [{"en": "expresión tal cual en el texto", "es": "traducción natural al español",
"frase": "la frase COMPLETA del texto donde aparece, copiada sin cambios"}]}

OFERTA:
"""


def _hoy() -> str:
    return datetime.date.today().isoformat()

def _en_dias(n: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()

def _id(en: str) -> str:
    return hashlib.sha1(en.strip().lower().encode()).hexdigest()[:10]

def _emit(evento: str, payload: dict):
    try:
        socketio.emit(evento, payload)
    except Exception:
        pass


# ─── Persistencia ──────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault("tarjetas", {})
    data.setdefault("historial", {})      # fecha → nº de repasos ese día (para la racha)
    data.setdefault("ofertas_leidas", [])  # ids de oferta ya procesados
    if not data["tarjetas"]:
        for en, es, ej, nota in SEMILLA:
            data["tarjetas"][_id(en)] = _tarjeta(en, es, ej, nota, "semilla")
    return data

def _save(data: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, data, indent=1)

def _tarjeta(en, es, ejemplo, nota, origen, oferta=None) -> dict:
    return {"id": _id(en), "en": en, "es": es, "ejemplo": ejemplo, "nota": nota,
            "origen": origen, "oferta": oferta, "caja": 0, "proxima": None,
            "aciertos": 0, "fallos": 0, "creada": _hoy()}


# ─── Repaso ────────────────────────────────────────────────────────────────────
def _racha(historial: dict) -> int:
    dias, d = 0, datetime.date.today()
    if not historial.get(d.isoformat()):
        d -= datetime.timedelta(days=1)   # hoy aún no ha repasado: la racha sigue viva
    while historial.get(d.isoformat()):
        dias += 1
        d -= datetime.timedelta(days=1)
    return dias

def get_data() -> dict:
    data = _load()
    hoy  = _hoy()
    ts   = list(data["tarjetas"].values())
    vencidas = sorted((t for t in ts if t["caja"] > 0 and t["proxima"] and t["proxima"] <= hoy),
                      key=lambda t: (t["proxima"], t["caja"]))
    nuevas_hoy = sum(1 for t in ts if t.get("estreno") == hoy)
    # primero lo que sale de TUS ofertas, luego la semilla
    nuevas = sorted((t for t in ts if t["caja"] == 0),
                    key=lambda t: (t["origen"] == "semilla", t["creada"]))[:max(0, NUEVAS_DIA - nuevas_hoy)]
    cola = (vencidas + nuevas)[:REPASO_MAX]
    return {
        "cola": cola,
        "stats": {
            "total": len(ts),
            "aprendidas": sum(1 for t in ts if t["caja"] >= 4),
            "en_curso": sum(1 for t in ts if 0 < t["caja"] < 4),
            "sin_empezar": sum(1 for t in ts if t["caja"] == 0),
            "de_ofertas": sum(1 for t in ts if t["origen"] == "oferta"),
            "pendientes_hoy": len(cola),
            "hechas_hoy": data["historial"].get(hoy, 0),
            "racha": _racha(data["historial"]),
        },
        "todas": sorted(ts, key=lambda t: (-t["caja"], t["en"].lower())),
    }

@_exclusivo
def repasar(tid: str, acierto: bool) -> bool:
    data = _load()
    t = data["tarjetas"].get(tid)
    if not t:
        return False
    hoy = _hoy()
    if t["caja"] == 0:
        t["estreno"] = hoy
    if acierto:
        t["caja"] = min(len(INTERVALOS) - 1, t["caja"] + 1)
        t["aciertos"] += 1
    else:
        t["caja"] = 1
        t["fallos"] += 1
    t["proxima"] = _en_dias(INTERVALOS[t["caja"]])
    data["historial"][hoy] = data["historial"].get(hoy, 0) + 1
    _save(data)
    return True

@_exclusivo
def borrar(tid: str) -> bool:
    data = _load()
    if data["tarjetas"].pop(tid, None) is None:
        return False
    _save(data)
    return True


# ─── Extraer vocabulario de las ofertas ────────────────────────────────────────
def _frase_con(texto: str, termino: str) -> str:
    """Frase del texto que contiene el término (por si el modelo la copió mal)."""
    for frase in re.split(r"(?<=[.!?;:])\s+|\n+", texto):
        if termino.lower() in frase.lower():
            return frase.strip()[:240]
    return ""

_STOP_EN = re.compile(r"\b(the|and|of|to|in|with|you|will|our|for|experience|skills|team|years)\b", re.I)
_STOP_ES = re.compile(r"\b(el|la|los|las|de|y|en|por|con|para|del|una|experiencia|equipo|años|que)\b", re.I)

def _idioma(texto: str) -> str:
    return "en" if len(_STOP_EN.findall(texto)) > len(_STOP_ES.findall(texto)) else "es"

def _parece_ingles(t: str) -> bool:
    return bool(re.search(r"[a-z]", t, re.I)) and not re.search(r"[áéíóúñ¿¡]", t, re.I) \
        and len(_STOP_ES.findall(t)) <= len(_STOP_EN.findall(t))

def _terminos_en(desc: str, terminos: list) -> list:
    """Oferta en inglés: expresiones que están literalmente en el texto."""
    salida = []
    for t in terminos:
        en = str(t.get("en", "")).strip().strip(".,;:")
        es = str(t.get("es", "")).strip()
        if not (2 < len(en) <= 60 and es) or en.lower() not in desc.lower() or not _parece_ingles(en):
            continue
        frase = str(t.get("frase", "")).strip()
        if not frase or en.lower() not in frase.lower() or frase.lower() not in desc.lower():
            frase = _frase_con(desc, en)
        salida.append({"en": en, "es": es[:120], "ejemplo": frase[:240], "modo": "en"})
    return salida

def _terminos_es(desc: str, terminos: list) -> list:
    """Oferta en español: frases del texto y cómo decirlas en inglés (para entrevistas)."""
    salida = []
    for t in terminos:
        es = str(t.get("es", "")).strip().strip(".,;:")
        en = str(t.get("en", "")).strip().strip(".,;:")
        # la frase en español tiene que estar en la oferta; la inglesa, ser inglés de verdad
        if not (4 < len(es) <= 80 and 2 < len(en) <= 80) or es.lower() not in desc.lower():
            continue
        # si la «traducción» está tal cual en la oferta española, es que no tradujo
        if len(es.split()) < 2 or not _parece_ingles(en) or en.lower() in desc.lower():
            continue
        salida.append({"en": en, "es": es, "ejemplo": _frase_con(desc, es), "modo": "es"})
    return salida

def extraer(n: int = 6, modelo: str = MODELO):
    """Lee las n ofertas mejor puntuadas aún no leídas y saca su vocabulario en inglés."""
    if not _extrayendo.acquire(blocking=False):
        log("🇬🇧 Ya estoy sacando vocabulario de las ofertas; espera a que acabe")
        return
    try:
        import ofertas
        data   = _load()
        leidas = set(data["ofertas_leidas"])
        od     = ofertas._load()
        prio   = {"entrevista": 0, "postulada": 1, "guardada": 2}
        candidatas = sorted(
            (it for it in od["items"].values()
             if it["id"] not in leidas and it.get("estado") not in ("descartada", "rechazada")
             # las manuales solo tienen texto si lo pegaste
             and (it["fuente"] != "manual" or it.get("descripcion"))),
            key=lambda i: (prio.get(i.get("estado"), 3),
                           -(i.get("eval", {}).get("encaje") or i.get("relevancia", 0))))[:n]
        if not candidatas:
            log("🇬🇧 No quedan ofertas nuevas de las que sacar vocabulario")
            return
        log(f"🇬🇧 Sacando vocabulario en inglés de {len(candidatas)} ofertas…")
        nuevas_total = 0
        for it in candidatas:
            try:
                desc = it.get("descripcion") or ofertas._descripcion(it)
            except Exception as e:
                log(f"  ⚠ «{it['titulo'][:40]}»: no pude leerla ({e})")
                continue
            if not desc:
                continue
            # guardar la descripción en la oferta: así «Evaluar» ya no la vuelve a descargar
            od = ofertas._load()
            if it["id"] in od["items"] and not od["items"][it["id"]].get("descripcion"):
                od["items"][it["id"]]["descripcion"] = desc[:8000]
                ofertas._save(od)
            idioma = _idioma(desc)
            try:
                r = _ollama_post("/api/chat", {
                    "model": modelo, "format": "json", "stream": False, "think": False,
                    "options": {"temperature": 0.1},
                    "messages": [{"role": "user", "content":
                                  (PROMPT_EXTRAER if idioma == "en" else PROMPT_ES) + desc[:5000]}],
                }, timeout=300)
                terminos = _json_ollama(r).get("terminos", [])
            except Exception as e:
                log("⚠ No pude hablar con Ollama. Enciende «Ollama (motor IA)» en la pestaña "
                    f"Locales y vuelve a intentarlo. ({e})")
                return
            if not isinstance(terminos, list):
                terminos = []
            terminos = [t for t in terminos if isinstance(t, dict)]
            validos = _terminos_en(desc, terminos) if idioma == "en" else _terminos_es(desc, terminos)
            with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
                data = _load()
                nuevas = 0
                for v in validos:
                    tid = _id(v["en"])
                    if tid in data["tarjetas"]:
                        continue
                    t = _tarjeta(v["en"], v["es"], v["ejemplo"], "", "oferta",
                                 {"titulo": it["titulo"][:80], "empresa": it.get("empresa", "")})
                    t["modo"] = v["modo"]
                    data["tarjetas"][tid] = t
                    nuevas += 1
                data["ofertas_leidas"].append(it["id"])
                _save(data)
            nuevas_total += nuevas
            log(f"  🇬🇧 «{it['titulo'][:45]}»: {nuevas} expresiones nuevas")
            time.sleep(ofertas.PAUSA)
        log(f"🇬🇧 Listo: {nuevas_total} expresiones nuevas de tus ofertas")
        _emit("ingles_updated", {"nuevas": nuevas_total})
    finally:
        _extrayendo.release()


def encolar_extraccion(n: int = 6):
    """Tras evaluar ofertas, la cola IA saca su vocabulario sin que pulses nada.
    Va detrás de las evaluaciones: así elige por encaje y la descripción ya está bajada."""
    import cola_ia
    cola_ia.encolar("ingles:extraer", f"sacar inglés de {n} ofertas", lambda: extraer(n))


# ─── Pronunciación ─────────────────────────────────────────────────────────────
def audio(tid: str, que: str = "en") -> str:
    """Ruta a un WAV con la pronunciación (término o frase de ejemplo). Se genera
    una vez y queda en caché. Devuelve "" si no se puede."""
    t = _load()["tarjetas"].get(tid)
    if not t or que not in ("en", "ejemplo"):
        return ""
    # en modo «es» el ejemplo es la frase española de la oferta: no se lee en inglés
    texto = t["en"] if que == "en" or t.get("modo") == "es" else t.get("ejemplo", "")
    if not texto:
        return ""
    nombre = hashlib.sha1(f"{VOZ}|{texto}".encode()).hexdigest()[:16] + ".wav"
    ruta = os.path.join(AUDIO_DIR, nombre)
    if os.path.isfile(ruta):
        return ruta
    import wave
    with _voz_lock:
        if _voz["modelo"] is None:
            from piper import PiperVoice
            _voz["modelo"] = PiperVoice.load(os.path.join(VOZ_DIR, VOZ + ".onnx"))
        os.makedirs(AUDIO_DIR, exist_ok=True)
        tmp = ruta + ".tmp"
        with wave.open(tmp, "wb") as w:
            _voz["modelo"].synthesize_wav(texto, w)
        os.replace(tmp, ruta)
    return ruta

def _precalentar():
    time.sleep(90)   # después del arranque, para no competir con becas/ofertas
    for tid in list(_load()["tarjetas"]):
        try:
            audio(tid, "en")
        except Exception as e:
            log(f"⚠ Pronunciación: no pude preparar el audio ({e})")
            return

def start_audio_precalentar():
    threading.Thread(target=_precalentar, daemon=True).start()
