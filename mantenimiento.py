"""
Centro de Control PRO — mantenimiento.py
Chequeo automático de los problemas que ya han pasado en este equipo, para
enterarse antes de que molesten:

  discos llenos · logs que crecen sin control (OneDrive llegó a 100 GB) ·
  journal grande · Ollama sin GPU (CDI de NVIDIA perdido tras actualizar) ·
  reinicio pendiente por kernel nuevo · actualizaciones · Tailscale caído ·
  OneDriveGUI cerrado · espacio recuperable en Podman · caché de pip ·
  copia de datos · buscadores de ofertas/becas que han dejado de funcionar

Cada chequeo devuelve {id, titulo, estado: ok|info|warn|err, detalle, arreglo}.
`arreglo` es un comando para copiar (lo que pide sudo, lo corre el usuario) o una
acción de un clic de la lista blanca ACCIONES (solo cosas seguras y reversibles).
Corre a los 2 min del arranque y cada 6 h; avisa por notificación si aparece
algo nuevo en rojo o ámbar.
"""

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time

from status import log

DISCOS    = [d.strip() for d in os.environ.get("DISCOS", "/").split(",") if d.strip()]
# carpeta donde vigilar las copias «safeBackup» que deja OneDrive (vacío = no se mira)
SAFEBACKUP_DIR = os.path.expanduser(os.environ.get("SAFEBACKUP_DIR", ""))
VMS_DISCO = os.environ.get("VMS_DISCO", "")   # disco donde viven las VMs (consejo específico)
LOGS      = ["~/.config/onedrive/logs/*", "~/.local/share/onedrivegui/*.log", "/tmp/onedrive-gui/*.log",
             "~/MiPanelControl/*.log", "~/rotate-onedrive-log.log"]
INTERVALO = 6 * 3600
_ultimo   = {"fecha": None, "checks": [], "corriendo": False}
_lock     = threading.Lock()


def _run(cmd: list, timeout: int = 20) -> tuple:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return -1, str(e)

def _mb(n: int) -> str:
    return f"{n / 1024**3:.1f} GB" if n >= 1024**3 else f"{n / 1024**2:.0f} MB"

def _c(id_, titulo, estado, detalle, arreglo=None):
    return {"id": id_, "titulo": titulo, "estado": estado, "detalle": detalle, "arreglo": arreglo}


# ─── Chequeos ──────────────────────────────────────────────────────────────────
def _discos():
    salida = []
    for d in DISCOS:
        if not os.path.ismount(d) and d != "/":
            salida.append(_c(f"disco{d}", f"Disco {d}", "warn", "No está montado"))
            continue
        u = shutil.disk_usage(d)
        pct = round(100 * u.used / (u.used + u.free))   # como df: sin contar lo reservado para root
        estado = "err" if pct >= 95 else "warn" if pct >= 85 else "ok"
        consejo = None
        if estado != "ok" and d == VMS_DISCO:
            consejo = {"texto": "Ahí viven las máquinas de VMware: borra las que no uses o sus instantáneas viejas"}
        salida.append(_c(f"disco{d}", f"Disco {d}", estado, f"{pct} % usado · {_mb(u.free)} libres", consejo))
    return salida

def _logs():
    grandes, total = [], 0
    for patron in LOGS:
        for f in glob.glob(os.path.expanduser(patron)):
            try:
                t = os.path.getsize(f)
            except OSError:
                continue
            total += t
            if t > 300 * 1024**2:
                grandes.append(f"{f.replace(os.path.expanduser('~'), '~')} ({_mb(t)})")
    if grandes:
        return [_c("logs", "Logs que crecen", "warn", "Muy grandes: " + "; ".join(grandes),
                   {"texto": "Si es el de OneDrive, mira debug_level en ~/.config/onedrive-gui/gui_settings "
                             "(las actualizaciones lo devuelven a DEBUG)"})]
    return [_c("logs", "Logs que crecen", "ok", f"Todo bajo control ({_mb(total)} entre todos)")]

def _journal():
    rc, out = _run(["journalctl", "--disk-usage"])
    m = re.search(r"take up ([\d.]+)([KMGT])", out)
    if not m:
        return [_c("journal", "Journal del sistema", "info", "No pude medirlo")]
    mb = float(m.group(1)) * {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024**2}[m.group(2)]
    estado = "warn" if mb > 2048 else "ok"
    return [_c("journal", "Journal del sistema", estado, f"{mb / 1024:.1f} GB",
               {"comando": "sudo journalctl --vacuum-time=7d"} if estado != "ok" else None)]

def _gpu_ollama():
    rc, out = _run(["podman", "ps", "--filter", "name=^ollama$", "--format", "{{.Names}}"])
    if "ollama" not in out:
        return [_c("gpu", "GPU para la IA local", "info", "Sin comprobar: Ollama está apagado")]
    rc, out = _run(["podman", "exec", "ollama", "nvidia-smi", "-L"], timeout=15)
    if rc == 0 and "GPU" in out:
        return [_c("gpu", "GPU para la IA local", "ok", out.strip().splitlines()[0][:80])]
    return [_c("gpu", "GPU para la IA local", "err",
               "Ollama no ve la GPU: los modelos irán lentísimos por CPU. Suele pasar tras actualizar "
               "el driver de NVIDIA o el kernel (el fichero CDI queda viejo).",
               {"comando": "sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml",
                "texto": "Después, apaga y enciende «Ollama (motor IA)»"})]

def _reinicio():
    actual = os.uname().release
    kernels = sorted((os.path.basename(k)[len("vmlinuz-"):] for k in glob.glob("/boot/vmlinuz-*")),
                     key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r"[.+-]", v)])
    nuevo = kernels[-1] if kernels else actual
    if os.path.exists("/var/run/reboot-required") or nuevo != actual:
        return [_c("reinicio", "Reinicio pendiente", "warn",
                   f"Hay un kernel nuevo instalado ({nuevo}) y sigues con {actual}. "
                   "Tras reiniciar comprueba la GPU de la IA y los módulos de VMware.")]
    return [_c("reinicio", "Reinicio pendiente", "ok", f"No (kernel {actual})")]

def _actualizaciones():
    rc, out = _run(["apt", "list", "--upgradable"], timeout=30)
    n = len([l for l in out.splitlines() if "/" in l and "upgradable" in l])
    estado = "warn" if n > 30 else "info" if n else "ok"
    return [_c("apt", "Actualizaciones del sistema", estado,
               f"{n} paquetes por actualizar" if n else "Al día (según la última consulta de apt)",
               {"comando": "sudo apt update && sudo apt upgrade"} if n else None)]

def _tailscale():
    rc, out = _run(["tailscale", "status", "--json"])
    try:
        estado = json.loads(out).get("BackendState")
    except Exception:
        estado = None
    if estado == "Running":
        return [_c("tailscale", "Tailscale", "ok", "Conectado")]
    return [_c("tailscale", "Tailscale", "err", f"No está conectado ({estado or 'sin respuesta'})",
               {"comando": "sudo tailscale up"})]

def _onedrive():
    if not os.path.isdir(os.path.expanduser("~/.config/onedrive")):
        return []   # este equipo no usa el cliente de OneDrive
    rc, out = _run(["pgrep", "-f", "OneDriveGUI"])
    if rc == 0:
        return [_c("onedrive", "OneDrive", "ok", "La GUI está abierta y sincronizando")]
    return [_c("onedrive", "OneDrive", "warn", "OneDriveGUI no está abierto: no se sincroniza nada",
               {"texto": "Ábrelo desde la tarjeta OneDrive (pestaña Sistema). Nunca lances «onedrive» por terminal con la GUI abierta."})]

def _podman():
    rc, out = _run(["podman", "system", "df", "--format", "json"], timeout=40)
    try:
        filas = json.loads(out)
        img = next(f for f in filas if f.get("Type") == "Images")
        recuperable = int(img.get("RawReclaimable") or 0)
    except Exception:
        return [_c("podman", "Espacio en Podman", "info", "No pude medirlo")]
    rc, colgantes = _run(["podman", "images", "-f", "dangling=true", "-q"])
    n_colg = len(colgantes.split())
    estado = "warn" if recuperable > 20 * 1024**3 else "ok"
    return [_c("podman", "Espacio en Podman", estado,
               f"{_mb(recuperable)} en imágenes que no usa ningún contenedor"
               + (f" · {n_colg} imagen{'es' if n_colg > 1 else ''} huérfana{'s' if n_colg > 1 else ''} (sin nombre)" if n_colg else ""),
               {"accion": "podman_prune", "boton": f"🧹 Borrar {'las ' + str(n_colg) + ' huérfanas' if n_colg > 1 else 'la huérfana'}",
                "comando": "podman image prune -a   # TODAS las no usadas: revisa antes, incluye imágenes de labs"}
               if n_colg or estado != "ok" else None)]

def _pip():
    ruta = os.path.expanduser("~/.cache/pip")
    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(ruta) for f in fs
                if os.path.isfile(os.path.join(r, f))) if os.path.isdir(ruta) else 0
    estado = "warn" if total > 2 * 1024**3 else "ok"
    return [_c("pip", "Caché de pip", estado, _mb(total),
               {"accion": "pip_purge", "boton": "🧹 Vaciar caché"} if total > 300 * 1024**2 else None)]

def _copia():
    import copias
    e = copias.get_estado()
    if e.get("error") and not e.get("ultima"):
        return [_c("copia", "Copia de tus datos", "err", e["error"], {"accion": "copia", "boton": "💾 Copiar ahora"})]
    if not e.get("ultima"):
        return [_c("copia", "Copia de tus datos", "warn", "Todavía no hay ninguna copia",
                   {"accion": "copia", "boton": "💾 Copiar ahora"})]
    dias = e.get("dias", 0)
    estado = "warn" if dias > 2 else "ok"
    return [_c("copia", "Copia de tus datos", estado,
               f"Última: {e['ultima'].replace('T', ' ')} ({e['tamano'] // 1024} KB, {e.get('copias', 1)} en OneDrive). "
               "Solo se hace otra cuando cambia algo.",
               {"accion": "copia", "boton": "💾 Copiar ahora"})]

def _fuentes():
    import salud_fuentes
    salida = []
    fuentes = salud_fuentes.estado()
    if not fuentes:
        return [_c("fuentes", "Buscadores de ofertas y becas", "info",
                   "Sin datos todavía: se comprobará en la próxima búsqueda de ofertas y becas")]
    for nombre, f in fuentes.items():
        if f["rota"] and f.get("motivo") == "captcha":
            salida.append(_c(f"fuente-{nombre}", f"Buscador: {f['etiqueta']}", "info",
                             f"Lleva {f['ceros']} búsquedas mostrando un captcha en vez de ofertas. Suele pasar "
                             "a ratos; si dura días, la web está bloqueando las búsquedas automáticas.",
                             {"texto": "Mientras tanto, busca en la web y usa «Añadir una oferta que encontraste por tu cuenta»"}))
        elif f["rota"]:
            salida.append(_c(f"fuente-{nombre}", f"Buscador: {f['etiqueta']}", "warn",
                             f"Lleva {f['ceros']} búsquedas seguidas sin traer nada (antes traía ~{f['media']}). "
                             "Probablemente la web ha cambiado y hay que ajustar el lector.",
                             {"texto": "Pídeselo a Claude: «el lector de " + f["etiqueta"] + " ha dejado de funcionar»"}))
    if not salida:
        salida.append(_c("fuentes", "Buscadores de ofertas y becas", "ok",
                         "Todos trajeron resultados en su última búsqueda"))
    return salida

def _safebackup():
    """OneDrive crea «-safeBackup-NNNN» cuando una app reescribe un fichero mientras se sincroniza
    (la plataforma AZ-104 llegó a 173 copias de su progreso, ~200 MB)."""
    base = SAFEBACKUP_DIR
    if not base or not os.path.isdir(base):
        return []
    copias = glob.glob(os.path.join(base, "**", "*-safeBackup-*"), recursive=True)
    if not copias:
        return [_c("safebackup", "Copias de conflicto de OneDrive", "ok", "Ninguna en la carpeta de estudio")]
    por_carpeta = {}
    for f in copias:
        if os.path.isfile(f):
            d = por_carpeta.setdefault(os.path.dirname(f).replace(base + "/", ""), [0, 0])
            d[0] += 1
            d[1] += os.path.getsize(f)
    top = sorted(por_carpeta.items(), key=lambda kv: -kv[1][0])[:3]
    detalle = " · ".join(f"{n} en {c} ({_mb(t)})" for c, (n, t) in top)
    return [_c("safebackup", "Copias de conflicto de OneDrive", "warn" if len(copias) > 20 else "info",
               f"{len(copias)} ficheros «safeBackup»: {detalle}",
               {"texto": "Ojo: a veces la copia «safeBackup» ES el fichero bueno (si el original se renombró en "
                         "un conflicto). Revisa antes de borrar nada."})]

# servicios que se sabe que deben escuchar en toda la red (separados por comas en .env)
PUERTOS_ESPERADOS = {p.strip() for p in os.environ.get("PUERTOS_ESPERADOS", "1716").split(",") if p.strip()}

def _expuestos():
    import redes
    abiertos = [p for p in redes.escuchando() if p["alcance"] == "toda la red" and str(p["puerto"]) not in PUERTOS_ESPERADOS]
    if not abiertos:
        return [_c("expuestos", "Servicios abiertos a toda tu red", "ok", "Ninguno inesperado")]
    lista = ", ".join(f":{p['puerto']} ({p['proceso']})" for p in abiertos)
    return [_c("expuestos", "Servicios abiertos a toda tu red", "warn",
               f"Escuchan en 0.0.0.0 y los puede usar cualquiera conectado a tu WiFi: {lista}",
               {"texto": "Si solo los usas desde este equipo, arráncalos en 127.0.0.1 (p. ej. -p 127.0.0.1:8080:8080 "
                         "en Podman, u OLLAMA_HOST=127.0.0.1). Si deben estar abiertos, añádelos a PUERTOS_ESPERADOS en .env."})]

CHEQUEOS = [_copia, _safebackup, _expuestos, _fuentes, _discos, _gpu_ollama, _logs, _journal, _reinicio, _tailscale,
            _onedrive, _podman, _pip, _actualizaciones]


# ─── Acciones de un clic (lista blanca) ────────────────────────────────────────
def _accion_copia():
    import copias
    copias.copiar("manual")

def _accion_pip():
    pip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "pip")
    rc, out = _run([pip, "cache", "purge"], timeout=120)
    log(f"🧹 Caché de pip: {out.strip().splitlines()[-1] if out.strip() else 'vaciada'}")

def _accion_podman():
    rc, out = _run(["podman", "image", "prune", "-f"], timeout=300)
    n = len([l for l in out.splitlines() if re.match(r"^[0-9a-f]{12,}", l)])
    log(f"🧹 Podman: {n} imágenes huérfanas borradas")

ACCIONES = {"copia": _accion_copia, "pip_purge": _accion_pip, "podman_prune": _accion_podman}

def accion(nombre: str):
    fn = ACCIONES.get(nombre)
    if fn:
        fn()
        revisar()


# ─── Ejecución ─────────────────────────────────────────────────────────────────
def revisar() -> dict:
    with _lock:
        _ultimo["corriendo"] = True
    resultados = {}
    def uno(fn):
        try:
            resultados[fn.__name__] = fn()
        except Exception as e:
            resultados[fn.__name__] = [_c(fn.__name__.strip("_"), fn.__name__.strip("_"), "info", f"Error al comprobar: {e}")]
    hilos = [threading.Thread(target=uno, args=(fn,)) for fn in CHEQUEOS]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    checks = [c for fn in CHEQUEOS for c in resultados.get(fn.__name__, [])]
    previos = {c["id"]: c["estado"] for c in _ultimo["checks"]}
    with _lock:
        _ultimo.update({"fecha": datetime.datetime.now().isoformat(timespec="minutes"),
                        "checks": checks, "corriendo": False})
    nuevos = [c for c in checks if c["estado"] in ("warn", "err") and previos.get(c["id"]) != c["estado"]]
    if nuevos and previos:
        try:
            from plyer import notification as _n
            _n.notify(title="🩺 Mantenimiento", message=" · ".join(c["titulo"] for c in nuevos)[:240], timeout=10)
        except Exception:
            pass
    return get_data()

def get_data() -> dict:
    checks = _ultimo["checks"]
    return {"fecha": _ultimo["fecha"], "corriendo": _ultimo["corriendo"], "checks": checks,
            "avisos": sum(1 for c in checks if c["estado"] in ("warn", "err")),
            "errores": sum(1 for c in checks if c["estado"] == "err")}

def _bucle():
    time.sleep(120)
    while True:
        try:
            revisar()
        except Exception as e:
            log(f"⚠ Mantenimiento: {e}")
        time.sleep(INTERVALO)

def start_mantenimiento():
    threading.Thread(target=_bucle, daemon=True).start()
