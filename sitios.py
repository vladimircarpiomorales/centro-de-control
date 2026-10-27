"""
Centro de Control PRO — sitios.py
Sirve la lista de dominios que yt-dlp sabe extraer, para que la extensión de Brave
la mantenga al día sola.

Por qué como subproceso: el venv del panel NO tiene yt-dlp instalado, solo el de
MeTube — que es además el que hace las descargas de verdad. Preguntarle a otro
intérprete daría una lista que no se corresponde con lo que realmente funciona
(el mismo desajuste que provoca los 403 cuando yt-dlp se queda viejo).
"""

import json
import os
import subprocess
import threading
import time

PYTHON_METUBE = os.path.expanduser(
    os.environ.get("PYTHON_METUBE", "~/MiPanelControl/metube/venv/bin/python")
)
GENERADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generar_sitios.py")
TIMEOUT = int(os.environ.get("SITIOS_TIMEOUT", 60))
TTL = int(os.environ.get("SITIOS_TTL", 3600))       # relanzar como mucho cada hora

_cache = {"ts": 0, "datos": None}
_lock = threading.Lock()


def listar(forzar: bool = False) -> dict:
    """{version, n, dominios} — cacheado en memoria durante TTL segundos."""
    with _lock:
        if not forzar and _cache["datos"] and time.time() - _cache["ts"] < TTL:
            return _cache["datos"]

        if not os.path.isfile(PYTHON_METUBE):
            return {"error": "No encuentro el yt-dlp de MeTube", "dominios": []}

        try:
            r = subprocess.run(
                [PYTHON_METUBE, GENERADOR, "--stdout"],
                capture_output=True, text=True, timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"El generador no respondió en {TIMEOUT}s", "dominios": []}

        if r.returncode != 0 or not r.stdout.strip():
            detalle = (r.stderr or "").strip().splitlines()
            return {"error": detalle[-1][:200] if detalle else "El generador falló",
                    "dominios": []}

        try:
            datos = json.loads(r.stdout)
        except json.JSONDecodeError:
            return {"error": "El generador devolvió algo que no es JSON", "dominios": []}

        _cache.update(ts=time.time(), datos=datos)
        return datos
