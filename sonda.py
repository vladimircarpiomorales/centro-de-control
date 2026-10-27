"""
Centro de Control PRO — sonda.py
Comprueba si una URL se puede descargar, SIN descargarla.

Corre yt-dlp en modo --simulate y traduce su error a un veredicto legible. Usa el
yt-dlp del venv de MeTube a propósito: es el que hará la descarga de verdad, y
versiones distintas dan respuestas distintas (un sitio que falla en una funciona
en otra). Preguntarle a otro intérprete daría un veredicto que no se cumple.
"""

import os
import re
import subprocess

PYTHON_METUBE = os.path.expanduser(
    os.environ.get("PYTHON_METUBE", "~/MiPanelControl/metube/venv/bin/python")
)
COOKIES_METUBE = os.path.expanduser(
    os.environ.get("COOKIES_METUBE", "~/MiPanelControl/metube/cookies.txt")
)
TIMEOUT = int(os.environ.get("SONDA_TIMEOUT", 30))

# El orden importa: "Sign in to confirm your age" también contiene "sign in", así
# que lo específico va antes que lo genérico.
PATRONES = [
    ("sin_soporte",   r"unsupported url|no video formats found|is not a valid url"),
    ("drm",           r"drm|protected by|widevine|playready"),
    ("edad",          r"confirm your age|age-restricted|inappropriate for some users"),
    ("necesita_login", r"sign in|log in|login required|private video|members[- ]only|"
                       r"requires? (a )?(subscription|authentication|purchase)|"
                       r"only available to|paid members|premium|cookies"),
    # Sin exigir el "not" delante: yt-dlp dice "has not made this video available
    # in your country", donde la negación va lejos del resto de la frase.
    ("geo",           r"available (in|from) your (country|location)|geo[- ]?(restrict|block)|"
                      r"blocked it in your country"),
    ("no_disponible", r"video unavailable|has been removed|no longer available|deleted|"
                      r"account (was )?terminated|this video is unavailable"),
    ("en_vivo",       r"is (currently )?live|live event will begin"),
    # Al final: un fallo de red se reconoce por descarte, y su texto ("unable to
    # download webpage") aparece también en errores más específicos de arriba.
    ("sin_conexion",  r"name or service not known|failed to resolve|connection refused|"
                      r"timed out|unable to download webpage|network is unreachable"),
]

MENSAJES = {
    "ok":             "Compatible — se puede descargar",
    "sin_soporte":    "yt-dlp no tiene extractor para este sitio",
    "necesita_login": "Necesita tu sesión — sube las cookies del sitio",
    "drm":            "Protegido con DRM — no se puede descargar",
    "edad":           "Restringido por edad — sube las cookies del sitio",
    "geo":            "Bloqueado en tu país",
    "no_disponible":  "El video ya no existe o fue retirado",
    "en_vivo":        "Es una emisión en directo",
    "sin_conexion":   "No pude alcanzar el sitio — ¿existe? ¿tienes red?",
    "lento":          f"Sin respuesta en {TIMEOUT}s — puede que igual funcione",
    "error":          "yt-dlp falló por otro motivo",
    "sin_metube":     "No encuentro el yt-dlp de MeTube",
}


def _clasificar(stderr: str) -> str:
    bajo = stderr.lower()
    for estado, patron in PATRONES:
        if re.search(patron, bajo):
            return estado
    return "error"


def probar(url: str) -> dict:
    """Devuelve {estado, mensaje, titulo, duracion, sitio, detalle}."""
    if not url.startswith(("http://", "https://")):
        return {"estado": "sin_soporte", "mensaje": "No es una URL http(s)"}

    if not os.path.isfile(PYTHON_METUBE):
        return {"estado": "sin_metube", "mensaje": MENSAJES["sin_metube"]}

    # Separador raro a propósito: los títulos traen "|", "-" y ":" a menudo.
    cmd = [
        PYTHON_METUBE, "-m", "yt_dlp",
        "--simulate", "--no-playlist", "--no-warnings", "--no-progress",
        "--socket-timeout", "10",
        "--print", "%(title)s\x1f%(duration)s\x1f%(extractor_key)s",
    ]
    # Si MeTube tiene cookies cargadas, sondear con ellas: si no, un sitio que SÍ
    # funcionaría diría "necesita login" y el veredicto sería falso.
    if os.path.isfile(COOKIES_METUBE):
        cmd += ["--cookies", COOKIES_METUBE]
    cmd.append(url)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"estado": "lento", "mensaje": MENSAJES["lento"]}
    except Exception as e:
        return {"estado": "error", "mensaje": MENSAJES["error"], "detalle": str(e)}

    if r.returncode == 0 and r.stdout.strip():
        partes = r.stdout.strip().splitlines()[0].split("\x1f")
        titulo, duracion, sitio = (partes + ["", "", ""])[:3]
        seg = int(float(duracion)) if duracion.replace(".", "").isdigit() else None
        return {
            "estado": "ok",
            "mensaje": MENSAJES["ok"],
            "titulo": titulo,
            "duracion": f"{seg // 60}:{seg % 60:02d}" if seg else None,
            "sitio": sitio,
            "con_cookies": os.path.isfile(COOKIES_METUBE),
        }

    estado = _clasificar(r.stderr)
    # Solo la última línea de error: yt-dlp escupe trazas largas.
    detalle = next((l for l in reversed(r.stderr.strip().splitlines()) if l.strip()), "")
    return {
        "estado": estado,
        "mensaje": MENSAJES[estado],
        "detalle": re.sub(r"^ERROR:\s*", "", detalle)[:200],
    }
