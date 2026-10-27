"""
Centro de Control PRO — copias.py
Copia diaria de los datos personales del panel a OneDrive.

Qué entra: todos los *_data.json del panel (también los de módulos nuevos, sin
tocar esta lista), perfil.json, carrera_semilla.json, la carpeta cv/ y, de
~/.local/share/mipanelcontrol, lo que no se puede regenerar: estudio.json y las
imágenes de las tarjetas. Qué NO: .env (claves de API: no deben subir a la nube),
ni cachés, ventana o estado de las fuentes (se regeneran solos).
Un .tar.gz por día en la carpeta sincronizada de OneDrive, con 30 días de
historia. Si el contenido no cambió desde la última copia, no se crea otra.

Solo se escriben ficheros nuevos en la carpeta de OneDrive: nunca se toca el
cliente ni su configuración (ver las reglas de OneDrive en las notas).
"""

import datetime
import glob
import hashlib
import io
import json
import os
import tarfile
import threading
import time

from status import log

BASE      = os.path.dirname(os.path.abspath(__file__))
DESTINO   = os.path.expanduser(os.environ.get(
    "COPIAS_DIR", "~/OneDrive/MiPanelControl-copias"))
ORIGENES  = ["*_data.json", "perfil.json", "carrera_semilla.json", "cv"]   # dentro de BASE
LOCAL     = os.path.expanduser("~/.local/share/mipanelcontrol")
LOCALES   = ["estudio.json", "tarjetas"]                                    # dentro de LOCAL
EN_LOCAL  = "local-share/mipanelcontrol"                                    # dónde van en el .tar.gz
DIAS      = 30
ESTADO    = os.path.expanduser("~/.local/share/mipanelcontrol/copias.json")
_lock     = threading.Lock()


def _ficheros() -> list:
    """[(ruta en disco, nombre dentro del .tar.gz)], ordenado por nombre."""
    salida = []
    def anadir(base, patron, prefijo):
        for ruta in glob.glob(os.path.join(base, patron)):
            if os.path.isfile(ruta):
                salida.append((ruta, os.path.join(prefijo, os.path.relpath(ruta, base))))
            elif os.path.isdir(ruta):
                for raiz, _, fs in os.walk(ruta):
                    salida.extend((os.path.join(raiz, f), os.path.join(prefijo, os.path.relpath(os.path.join(raiz, f), base)))
                                  for f in sorted(fs) if not f.endswith((".tmp", ".pdf")))
    for o in ORIGENES:
        anadir(BASE, o, "")
    for o in LOCALES:
        anadir(LOCAL, o, EN_LOCAL)
    return sorted(salida, key=lambda x: x[1])

def _huella(ficheros: list) -> str:
    h = hashlib.sha256()
    for ruta, nombre in ficheros:
        h.update(nombre.encode())
        with open(ruta, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:16]

def _estado() -> dict:
    try:
        with open(ESTADO) as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar_estado(e: dict):
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w") as f:
        json.dump(e, f)

def copiar(motivo: str = "diaria") -> dict:
    """Hace la copia si hace falta. Devuelve el estado."""
    with _lock:
        est = _estado()
        if not os.path.isdir(os.path.dirname(DESTINO)):
            est.update({"error": f"No encuentro la carpeta de OneDrive ({os.path.dirname(DESTINO)}). ¿Disco montado?",
                        "error_fecha": datetime.datetime.now().isoformat(timespec="minutes")})
            _guardar_estado(est)
            log(f"⚠ Copia de datos: {est['error']}")
            return est
        ficheros = _ficheros()
        huella = _huella(ficheros)
        hoy = datetime.date.today().isoformat()
        if est.get("huella") == huella and motivo != "manual":
            return est   # nada nuevo desde la última copia
        os.makedirs(DESTINO, exist_ok=True)
        nombre = f"panel-{hoy}.tar.gz"
        tmp = os.path.join(DESTINO, "." + nombre + ".tmp")   # OneDrive ignora los .tmp
        with tarfile.open(tmp, "w:gz") as tar:
            for ruta, en_tar in ficheros:
                tar.add(ruta, arcname=en_tar)
            leeme = (f"Copia del Centro de Control PRO — {datetime.datetime.now():%Y-%m-%d %H:%M}\n"
                     "Para restaurar (con el panel cerrado):\n"
                     "  tar -xzf este-fichero.tar.gz -C ~/MiPanelControl --exclude='local-share/*'\n"
                     "  tar -xzf este-fichero.tar.gz -C ~/.local/share --strip-components=1 local-share\n"
                     "No incluye .env (claves).\n").encode()
            info = tarfile.TarInfo("LEEME.txt")
            info.size, info.mtime = len(leeme), time.time()
            tar.addfile(info, io.BytesIO(leeme))
        os.replace(tmp, os.path.join(DESTINO, nombre))
        # historia: fuera las de más de DIAS días
        limite = (datetime.date.today() - datetime.timedelta(days=DIAS)).isoformat()
        for f in os.listdir(DESTINO):
            if f.startswith("panel-") and f.endswith(".tar.gz") and f[6:16] < limite:
                os.remove(os.path.join(DESTINO, f))
        est = {"huella": huella, "ultima": datetime.datetime.now().isoformat(timespec="minutes"),
               "fichero": nombre, "tamano": os.path.getsize(os.path.join(DESTINO, nombre)),
               "n_ficheros": len(ficheros), "destino": DESTINO,
               "copias": len([f for f in os.listdir(DESTINO) if f.startswith("panel-")])}
        _guardar_estado(est)
        log(f"💾 Copia de datos guardada en OneDrive ({nombre}, {est['tamano'] // 1024} KB)")
        return est

def get_estado() -> dict:
    est = _estado()
    if est.get("ultima"):
        est["dias"] = (datetime.date.today() - datetime.date.fromisoformat(est["ultima"][:10])).days
    return est

def _bucle():
    time.sleep(300)
    while True:
        try:
            copiar()
        except Exception as e:
            log(f"⚠ Copia de datos: {e}")
        time.sleep(6 * 3600)

def start_copias():
    threading.Thread(target=_bucle, daemon=True).start()
