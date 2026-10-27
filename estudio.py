"""
Centro de Control PRO — estudio.py
Tu estudio de certificaciones (app «Certificaciones», ~/Proyectos/lpi-2026, :7810)
resumido en la portada Hoy, sin tener que abrirla.

Lee en solo lectura los ficheros de progreso que guarda esa app
(lpi-<curso>-progreso.json en la carpeta de OneDrive): unidades hechas, unidades
marcadas «repasar» y preguntas de test respondidas (aciertos/fallos). La app no
guarda fechas, así que:
  - «última vez» = fecha de modificación del fichero de cada curso;
  - la racha la lleva este módulo: cada día anota la actividad total (unidades
    hechas + respuestas); si sube respecto al día anterior, ese día cuenta.
Los nombres y el total de unidades de cada curso salen de /cursos de la app
cuando está encendida (se guardan para cuando está apagada).
"""

import datetime
import glob
import json
import os
import re
import socket
import subprocess
import threading
import urllib.request
import almacen

DATOS_DIR = os.path.expanduser(os.environ.get(
    "ESTUDIO_DIR", "~/Proyectos/lpi-2026"))
APP_DIR   = os.path.expanduser(os.environ.get("ESTUDIO_APP", "~/Proyectos/lpi-2026"))
APP_URL   = "http://127.0.0.1:7810"
ESTADO    = os.path.expanduser("~/.local/share/mipanelcontrol/estudio.json")
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)


def _estado() -> dict:
    try:
        with open(ESTADO) as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar(e: dict):
    with _lock:
        os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
        almacen.guardar_json(ESTADO, e, indent=None)

def _app_encendida() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 7810), timeout=0.5):
            return True
    except OSError:
        return False

def _cursos_app() -> dict:
    """{codigo: {nombre, grupo, unidades}} desde la app (si está encendida)."""
    try:
        with urllib.request.urlopen(APP_URL + "/cursos", timeout=3) as r:
            d = json.load(r)
        return {c["codigo"]: {"nombre": c["nombre"], "grupo": c.get("grupo", ""), "unidades": c.get("unidades", 0)}
                for c in d.get("cursos", [])}
    except Exception:
        return {}

def _leer_progreso(ruta: str) -> dict:
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {}
    unidades = d.get("unidades") if isinstance(d.get("unidades"), dict) else {}
    test = d.get("test") if isinstance(d.get("test"), dict) else {}
    v = sum(int(x.get("v", 0)) for x in test.values() if isinstance(x, dict))
    f = sum(int(x.get("f", 0)) for x in test.values() if isinstance(x, dict))
    return {"hechas": sum(1 for u in unidades.values() if isinstance(u, dict) and u.get("hecho")),
            "repasar": sum(1 for u in unidades.values() if isinstance(u, dict) and u.get("repasar")),
            "aciertos": v, "fallos": f}

@_exclusivo
def get_data() -> dict:
    est = _estado()
    encendida = _app_encendida()
    if encendida:
        nombres = _cursos_app()
        if nombres:
            est["cursos"] = nombres
    nombres = est.get("cursos", {})
    hoy = datetime.date.today()
    cursos = []
    for ruta in glob.glob(os.path.join(DATOS_DIR, "lpi-*-progreso.json")):
        codigo = re.match(r"lpi-(.+)-progreso\.json", os.path.basename(ruta)).group(1)
        p = _leer_progreso(ruta)
        if not p:
            continue
        info = nombres.get(codigo, {})
        mtime = datetime.date.fromtimestamp(os.path.getmtime(ruta))
        cursos.append({"codigo": codigo, "nombre": info.get("nombre", codigo), "grupo": info.get("grupo", ""),
                       "unidades": info.get("unidades", 0), **p,
                       "ultima": mtime.isoformat(), "dias": (hoy - mtime).days})
    az = _az104()
    if az:
        cursos.append(az)
    cursos.sort(key=lambda c: c["ultima"], reverse=True)

    # racha: actividad total por día
    actividad = sum(c["hechas"] + c["aciertos"] + c["fallos"] for c in cursos)
    diario = est.setdefault("diario", {})
    diario[hoy.isoformat()] = actividad
    for k in sorted(diario)[:-60]:
        del diario[k]
    racha, d = 0, hoy
    if not _estudiado(diario, d):
        d -= datetime.timedelta(days=1)    # hoy aún no, pero la racha de ayer sigue viva
    while _estudiado(diario, d):
        racha += 1
        d -= datetime.timedelta(days=1)
    _guardar(est)

    examen = est.get("examen")
    if examen and examen.get("fecha"):
        try:
            examen["dias"] = (datetime.date.fromisoformat(examen["fecha"]) - hoy).days
        except ValueError:
            examen = None
    total_v = sum(c["aciertos"] for c in cursos)
    total_f = sum(c["fallos"] for c in cursos)
    return {"cursos": cursos, "app_encendida": encendida, "app_url": APP_URL, "racha": racha,
            "repasar": sum(c["repasar"] for c in cursos),
            "respuestas": total_v + total_f,
            "pct_aciertos": round(100 * total_v / (total_v + total_f)) if total_v + total_f else None,
            "examen": examen, "disponible": os.path.isdir(DATOS_DIR)}

def _estudiado(diario: dict, dia: datetime.date) -> bool:
    """Un día cuenta si su actividad supera la del último día anterior anotado."""
    k = dia.isoformat()
    if k not in diario:
        return False
    anteriores = [d for d in sorted(diario) if d < k]
    if not anteriores:
        return False    # primer día anotado: sin referencia, no se sabe
    return diario[k] > diario[anteriores[-1]]

@_exclusivo
def set_examen(nombre: str, fecha: str) -> bool:
    est = _estado()
    if not fecha:
        est.pop("examen", None)
    else:
        try:
            datetime.date.fromisoformat(fecha)
        except ValueError:
            return False
        est["examen"] = {"nombre": nombre.strip()[:40] or "Examen", "fecha": fecha}
    _guardar(est)
    return True

def abrir(codigo: str = "") -> bool:
    """Abre la app (la arranca si hace falta) en la portada o en un curso conocido."""
    script = os.path.join(APP_DIR, "arrancar.sh")
    if not os.path.isfile(script):
        return False
    if codigo and codigo not in _estado().get("cursos", {}):
        codigo = ""   # solo códigos que la app ha dicho que existen
    subprocess.Popen(["bash", script] + ([codigo] if codigo else []), cwd=APP_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True


# ─── AZ-104 (plataforma aparte, mismo formato de progreso) ─────────────────────
AZ_DIR      = os.path.expanduser(os.environ.get("AZ104_APP", "~/Proyectos/az104-2026"))
AZ_PROGRESO = os.path.expanduser(os.environ.get(
    "AZ104_PROGRESO", "~/Proyectos/az104-2026/progreso.json"))

def _az104() -> dict:
    p = _leer_progreso(AZ_PROGRESO)
    if not p:
        return {}
    total = 0
    try:
        with open(os.path.join(AZ_DIR, "build", "contenido.json"), encoding="utf-8") as f:
            c = json.load(f)
        total = sum(1 for r in c["rutas"] for m in r["modulos"] for u in m["unidades"] if u.get("tipo") != "quiz")
    except Exception:
        pass
    mtime = datetime.date.fromtimestamp(os.path.getmtime(AZ_PROGRESO))
    return {"codigo": "az104", "nombre": "AZ-104 Azure Administrator", "grupo": "Microsoft", "unidades": total,
            **p, "ultima": mtime.isoformat(), "dias": (datetime.date.today() - mtime).days}


# ─── Mapa de plataformas de estudio (~/Proyectos) ──────────────────────────────
UK_DIR = os.path.expanduser(os.environ.get("UK_TUTOR", "~/Proyectos/UK-English-Tutor"))
PROYECTOS = os.path.expanduser("~/Proyectos")

def _puerto_abierto(p: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", p), timeout=0.4):
            return True
    except OSError:
        return False

def _uk_progreso() -> dict:
    """Perfil con más XP del tutor de inglés (solo lectura de su SQLite)."""
    import sqlite3
    ruta = os.path.join(UK_DIR, "data", "progreso.db")
    if not os.path.isfile(ruta):
        return {}
    try:
        c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2)
        fila = c.execute("SELECT u.id, u.username, s.xp, s.streak, s.updated_at FROM users u "
                         "JOIN user_state s ON s.user_id = u.id ORDER BY s.xp DESC LIMIT 1").fetchone()
        if not fila:
            return {}
        hoy = datetime.date.today().isoformat()
        srs = c.execute("SELECT count(*), sum(due_date <= ?) FROM user_srs WHERE user_id = ?", (hoy, fila[0])).fetchone()
        semanas = c.execute("SELECT count(*) FROM user_ruta WHERE user_id = ?", (fila[0],)).fetchone()[0]
        c.close()
    except Exception:
        return {}
    ultima = (fila[4] or "")[:10]
    return {"perfil": fila[1], "xp": fila[2] or 0, "racha": fila[3] or 0, "srs": srs[0] or 0,
            "srs_hoy": srs[1] or 0, "semanas": semanas, "ultima": ultima,
            "dias": (datetime.date.today() - datetime.date.fromisoformat(ultima)).days if ultima else None}

def plataformas() -> list:
    d = get_data()
    lpi = [c for c in d["cursos"] if c["codigo"] != "az104"]
    az = next((c for c in d["cursos"] if c["codigo"] == "az104"), None)
    uk = _uk_progreso()
    salida = [
        {"id": "certificaciones", "nombre": "Certificaciones", "icono": "🐧",
         "que": "LPI (Essentials, LPIC-1, LPIC-2) y CCNA 1-2: teoría, test, retos, fichas, Shell Gym",
         "encendida": _puerto_abierto(7810), "url": APP_URL,
         "cursos": [{"codigo": c["codigo"], "nombre": c["nombre"], "hechas": c["hechas"], "unidades": c["unidades"],
                     "aciertos": c["aciertos"], "fallos": c["fallos"], "dias": c["dias"]} for c in lpi],
         "ultima": lpi[0]["ultima"] if lpi else None, "dias": lpi[0]["dias"] if lpi else None},
        {"id": "az104", "nombre": "AZ-104", "icono": "☁️",
         "que": "Microsoft Learn offline (6 rutas + 10 módulos), banco de preguntas, simulacro y labs",
         "encendida": _puerto_abierto(7799), "url": "http://127.0.0.1:7799/",
         "resumen": az, "ultima": az["ultima"] if az else None, "dias": az["dias"] if az else None},
        {"id": "uk", "nombre": "UK English Tutor", "icono": "🇬🇧",
         "que": "Inglés británico A1→C2: ruta de 64 semanas, SRS, speaking, audiolibros",
         "encendida": _puerto_abierto(8011), "url": "http://127.0.0.1:8011/",
         "resumen": uk, "ultima": uk.get("ultima"), "dias": uk.get("dias")},
        {"id": "ccna-labs", "nombre": "Labs CCNA (CML)", "icono": "🔀",
         "que": "Guía de CML con 135 fichas de labs (Odom/CertSkills y cml-community)",
         "encendida": None, "url": None, "ultima": None, "dias": None},
        {"id": "ccse", "nombre": "CCSE (nacionalidad)", "icono": "🇪🇸",
         "que": "Manual del Cervantes + las 300 preguntas del examen (un solo HTML)",
         "encendida": None, "url": None, "ultima": None, "dias": None},
    ]
    return salida

def abrir_plataforma(pid: str, codigo: str = "") -> bool:
    """Lista blanca: cada plataforma se abre a su manera. Nada viene de la petición salvo el id."""
    def lanzar(cmd, cwd):
        subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if pid == "certificaciones":
        return abrir(codigo)
    if pid == "az104":
        script = os.path.join(AZ_DIR, "arrancar.sh")
        if os.path.isfile(script):
            lanzar(["bash", script], AZ_DIR)
            return True
    if pid == "uk":
        if not _puerto_abierto(8011):
            # solo en este equipo: por defecto escucha en 0.0.0.0 (toda la red local)
            lanzar(["python3", "server.py", "--host", "127.0.0.1"], UK_DIR)
            for _ in range(20):
                if _puerto_abierto(8011):
                    break
                import time
                time.sleep(0.3)
        lanzar(["xdg-open", "http://127.0.0.1:8011/"], UK_DIR)
        return True
    if pid == "ccna-labs":
        guia = os.path.join(PROYECTOS, "ccna-labs", "guia-cml.html")
        if os.path.isfile(guia):
            lanzar(["xdg-open", guia], PROYECTOS)
            return True
    if pid == "ccse":
        html = os.path.join(PROYECTOS, "ccse-2026", "build", "ccse-estudio.html")
        if os.path.isfile(html):
            lanzar(["xdg-open", html], PROYECTOS)
            return True
    return False
