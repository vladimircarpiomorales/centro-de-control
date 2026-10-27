"""
Centro de Control PRO — laboratorios.py
Todo lo de prácticas en un sitio: máquinas de VMware Workstation, máquinas de
KVM/libvirt (las lpi-*, la de clase), Cisco Modeling Labs y los contenedores de
laboratorio que se quedan encendidos sin que nadie se acuerde.

Seguridad: la API solo acepta ids que este módulo ha listado (índice del
inventario de VMware, nombre de dominio de libvirt, id de contenedor «suelto»).
Nunca se pasa a vmrun/virsh/podman una ruta o nombre que venga de la petición.
Los contenedores de los servicios del panel (services.py) no se tocan aquí.
"""

import json
import os
import re
import subprocess
import threading
import time

from status import log
from services import SERVICES

INVENTARIO = os.path.expanduser("~/.vmware/inventory.vmls")
CML_VMX    = os.path.expanduser(os.environ.get("CML_VMX", "~/vmware/CML/cml.vmx"))
CML_URL    = os.environ.get("CML_URL", "https://cml.local")
CML_BIN    = os.path.expanduser("~/.local/bin/cml")
VIRSH      = ["virsh", "-c", "qemu:///system"]
_cache     = {"t": 0, "vmrun": set()}
_ocupado   = set()   # ids con una orden en marcha (para pintar «arrancando…»)


def _run(cmd: list, timeout: int = 20) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


# ─── VMware Workstation ────────────────────────────────────────────────────────
def _vmrun_encendidas() -> set:
    # vmrun list tarda ~1 s (carga su AppLoader): se cachea unos segundos
    if time.time() - _cache["t"] > 5:
        salida = _run(["vmrun", "list"])
        _cache["vmrun"] = {l.strip() for l in salida.splitlines() if l.strip().endswith(".vmx")}
        _cache["t"] = time.time()
    return _cache["vmrun"]

def _vmx_datos(ruta: str) -> dict:
    try:
        with open(ruta, errors="replace") as f:
            texto = f.read()
    except Exception:
        return {}
    def campo(k):
        m = re.search(rf'^{k} = "([^"]*)"', texto, re.M)
        return m.group(1) if m else ""
    return {"ram_mb": int(campo("memsize") or 0), "cpus": int(campo("numvcpus") or 1),
            "so": campo("guestOS")}

def vmware_vms() -> list:
    try:
        with open(INVENTARIO, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except Exception:
        return []
    items = {}
    for clave, campo, valor in re.findall(r'(vmlist\d+)\.(\w+) = "([^"]*)"', texto):
        items.setdefault(clave, {})[campo] = valor
    carpetas = {v.get("ItemID"): v.get("DisplayName") for v in items.values() if v.get("Type") == "2"}
    encendidas = _vmrun_encendidas()
    vms = []
    for clave, v in items.items():
        ruta = v.get("config", "")
        if not ruta.endswith(".vmx") or not os.path.isfile(ruta):
            continue
        vms.append({
            "id": clave, "nombre": v.get("DisplayName") or os.path.basename(ruta)[:-4],
            "carpeta": carpetas.get(v.get("ParentID"), ""), "favorita": v.get("IsFavorite") == "TRUE",
            "encendida": ruta in encendidas, "ocupada": clave in _ocupado,
            "es_cml": ruta == CML_VMX, **_vmx_datos(ruta),
        })
    vms.sort(key=lambda m: (not m["encendida"], not m["favorita"], m["carpeta"], m["nombre"].lower()))
    return vms

def _vmx_de(vid: str) -> str:
    try:
        with open(INVENTARIO, encoding="utf-8", errors="replace") as f:
            m = re.search(rf'^{re.escape(vid)}\.config = "([^"]*\.vmx)"', f.read(), re.M)
    except Exception:
        return ""
    return m.group(1) if m and os.path.isfile(m.group(1)) else ""

def vmware_accion(vid: str, accion: str):
    """Corre en background. accion: start (sin ventana) | gui | stop (apagado ordenado)."""
    vmx = _vmx_de(vid)
    if not vmx or accion not in ("start", "gui", "stop"):
        return
    nombre = os.path.basename(vmx)[:-4]
    _ocupado.add(vid)
    try:
        if accion == "stop":
            log(f"🧪 Apagando «{nombre}» (apagado ordenado)…")
            r = subprocess.run(["vmrun", "stop", vmx, "soft"], capture_output=True, text=True, timeout=180)
        else:
            log(f"🧪 Encendiendo «{nombre}»{' con ventana' if accion == 'gui' else ''}…")
            r = subprocess.run(["vmrun", "start", vmx, "gui" if accion == "gui" else "nogui"],
                               capture_output=True, text=True, timeout=180)
        error = (r.stdout + r.stderr).strip().splitlines()
        error = [l for l in error if "AppLoader" not in l and "libaio" not in l]
        log(f"  ⚠ vmrun: {' '.join(error)[:200]}" if r.returncode else f"  ✓ «{nombre}» {'apagada' if accion == 'stop' else 'encendida'}")
    except Exception as e:
        log(f"  ⚠ «{nombre}»: {e}")
    finally:
        _ocupado.discard(vid)
        _cache["t"] = 0


# ─── KVM / libvirt ─────────────────────────────────────────────────────────────
def kvm_vms() -> list:
    vms = []
    for linea in _run(VIRSH + ["list", "--all", "--name"]).splitlines():
        nombre = linea.strip()
        if not nombre:
            continue
        info = _run(VIRSH + ["dominfo", nombre])
        estado = re.search(r"^State:\s+(.+)$", info, re.M)
        ram = re.search(r"^Max memory:\s+(\d+) KiB", info, re.M)
        cpus = re.search(r"^CPU\(s\):\s+(\d+)", info, re.M)
        vms.append({"id": nombre, "nombre": nombre,
                    "encendida": bool(estado and estado.group(1).strip() == "running"),
                    "ocupada": nombre in _ocupado,
                    "ram_mb": int(ram.group(1)) // 1024 if ram else 0,
                    "cpus": int(cpus.group(1)) if cpus else 0})
    vms.sort(key=lambda m: (not m["encendida"], m["nombre"]))
    return vms

def kvm_accion(nombre: str, accion: str):
    if accion not in ("start", "stop") or nombre not in {v["id"] for v in kvm_vms()}:
        return
    _ocupado.add(nombre)
    try:
        orden = "start" if accion == "start" else "shutdown"
        log(f"🧪 {'Encendiendo' if accion == 'start' else 'Apagando'} «{nombre}» (KVM)…")
        r = subprocess.run(VIRSH + [orden, nombre], capture_output=True, text=True, timeout=60)
        log(f"  ⚠ virsh: {(r.stderr or r.stdout).strip()[:200]}" if r.returncode
            else f"  ✓ «{nombre}»: orden de {'encendido' if accion == 'start' else 'apagado'} enviada")
    except Exception as e:
        log(f"  ⚠ «{nombre}»: {e}")
    finally:
        _ocupado.discard(nombre)


# ─── Cisco Modeling Labs ───────────────────────────────────────────────────────
def cml_estado() -> dict:
    encendida = CML_VMX in _vmrun_encendidas()
    lista = False
    if encendida:
        salida = _run(["curl", "-sk", "-m", "3", f"{CML_URL}/api/v0/system_information"], timeout=5)
        lista = '"ready":true' in salida.replace(" ", "")
    return {"encendida": encendida, "lista": lista, "url": CML_URL,
            "ocupada": "cml" in _ocupado, "disponible": os.path.isfile(CML_BIN)}

def cml_accion(accion: str):
    """El script cml ya sabe hacerlo bien: al apagar, para los labs antes de la VM."""
    if accion not in ("on", "off") or not os.path.isfile(CML_BIN):
        return
    _ocupado.add("cml")
    log(f"🧪 CML: {'encendiendo (tarda 3-5 min)' if accion == 'on' else 'parando labs y apagando'}…")
    try:
        p = subprocess.Popen([CML_BIN, accion], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for linea in p.stdout:
            linea = linea.strip().strip(".")
            if linea:
                log(f"  {linea[:160]}")
        p.wait(timeout=600)
    except Exception as e:
        log(f"  ⚠ CML: {e}")
    finally:
        _ocupado.discard("cml")
        _cache["t"] = 0


# ─── Contenedores sueltos ──────────────────────────────────────────────────────
def _contenedores_de_servicios() -> set:
    nombres = set()
    def recoger(d):
        for k in ("containers", "container"):
            v = d.get(k)
            if isinstance(v, str):
                nombres.add(v)
            elif isinstance(v, list):
                nombres.update(v)
    for svc in SERVICES.values():
        recoger(svc)
        for act in (svc.get("actions") or {}).values():
            recoger(act)
    return nombres | {"ollama", "resume-chrome", "resume-db"}

def contenedores_sueltos() -> list:
    try:
        datos = json.loads(_run(["podman", "ps", "--format", "json"]) or "[]")
    except Exception:
        return []
    servicios = _contenedores_de_servicios()
    ahora = time.time()
    sueltos = []
    for c in datos:
        nombre = (c.get("Names") or ["?"])[0]
        if nombre in servicios:
            continue
        inicio = c.get("StartedAt") or 0
        sueltos.append({"id": c.get("Id", "")[:12], "nombre": nombre, "imagen": c.get("Image", ""),
                        "horas": round((ahora - inicio) / 3600, 1) if inicio else None,
                        "se_borra": bool(c.get("AutoRemove")),
                        "ocupada": c.get("Id", "")[:12] in _ocupado})
    sueltos.sort(key=lambda c: -(c["horas"] or 0))
    return sueltos

def parar_contenedores(ids: list):
    validos = {c["id"]: c for c in contenedores_sueltos()}
    elegidos = [validos[i] for i in ids if i in validos]
    if not elegidos:
        return
    log(f"🧪 Parando {len(elegidos)} contenedor{'es' if len(elegidos) > 1 else ''} de laboratorio…")
    for c in elegidos:
        _ocupado.add(c["id"])
    try:
        # paralelo: con -t 5 cada uno, en serie serían 35 s para 7
        procs = [subprocess.Popen(["podman", "stop", "-t", "5", c["id"]],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for c in elegidos]
        for p in procs:
            p.wait(timeout=60)
        log(f"  ✓ Parados: {', '.join(c['nombre'] for c in elegidos)}")
    except Exception as e:
        log(f"  ⚠ podman: {e}")
    finally:
        for c in elegidos:
            _ocupado.discard(c["id"])


# ─── Resumen ───────────────────────────────────────────────────────────────────
def _ram_disponible_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            m = re.search(r"^MemAvailable:\s+(\d+) kB", f.read(), re.M)
        return int(m.group(1)) // 1024 if m else 0
    except Exception:
        return 0

def get_data() -> dict:
    resultado = {}
    hilos = []
    # vmrun, virsh y podman tardan cada uno ~1 s: en paralelo
    for clave, fn in (("vmware", vmware_vms), ("kvm", kvm_vms), ("cml", cml_estado),
                      ("contenedores", contenedores_sueltos)):
        t = threading.Thread(target=lambda c=clave, f=fn: resultado.__setitem__(c, f()))
        t.start()
        hilos.append(t)
    for t in hilos:
        t.join(timeout=25)
    resultado.setdefault("vmware", [])
    resultado.setdefault("kvm", [])
    resultado.setdefault("contenedores", [])
    resultado.setdefault("cml", {"encendida": False, "lista": False, "url": CML_URL, "ocupada": False, "disponible": False})
    resultado["ram_disponible_mb"] = _ram_disponible_mb()
    return resultado
