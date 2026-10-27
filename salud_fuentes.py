"""
Centro de Control PRO — salud_fuentes.py
¿Ha dejado de funcionar algún buscador? Los lectores de ofertas y becas leen el
HTML de webs ajenas: cuando una cambia, el lector devuelve 0 en silencio.

Cada búsqueda registra cuántos resultados trajo cada fuente. Una fuente está
«rota» si lleva CEROS_ROTA búsquedas seguidas a cero y antes traía resultados
(un canal tranquilo un día no cuenta: tiene que haber traído algo antes).
Lo leen el chequeo de Mantenimiento y la pestaña Ofertas.
"""

import json
import os
import threading

FICHERO    = os.path.expanduser("~/.local/share/mipanelcontrol/fuentes.json")
HISTORIA   = 8
CEROS_ROTA = 2
_lock      = threading.Lock()


def _load() -> dict:
    try:
        with open(FICHERO) as f:
            return json.load(f)
    except Exception:
        return {}

def registrar(nombre: str, etiqueta: str, n: int, motivo: str = None):
    """motivo: por qué trajo 0 si se sabe (p. ej. «captcha»), para no confundirlo con un lector roto."""
    with _lock:
        d = _load()
        f = d.setdefault(nombre, {"etiqueta": etiqueta, "historia": []})
        f["etiqueta"] = etiqueta
        f["historia"] = (f["historia"] + [int(n)])[-HISTORIA:]
        f["motivo"] = motivo if not n else None
        os.makedirs(os.path.dirname(FICHERO), exist_ok=True)
        tmp = FICHERO + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh)
        os.replace(tmp, FICHERO)

def estado() -> dict:
    salida = {}
    for nombre, f in _load().items():
        h = f.get("historia", [])
        ceros = 0
        for n in reversed(h):
            if n:
                break
            ceros += 1
        previos = [n for n in h if n]
        salida[nombre] = {
            "etiqueta": f.get("etiqueta", nombre), "historia": h, "ceros": ceros,
            "media": round(sum(previos) / len(previos)) if previos else 0,
            "rota": ceros >= CEROS_ROTA and bool(previos), "motivo": f.get("motivo"),
        }
    return salida
