"""
Centro de Control PRO — redes.py
Kit de redes: calculadora de subredes, diagnóstico (ping, mtr, traceroute, DNS),
puertos en escucha y un vigilante de la red local.

  calcular(cidr)        → red, broadcast, rango útil, máscaras y binario (IPv4 e IPv6)
  diagnostico(tipo, x)  → salida de ping / mtr / traceroute / dig. El destino se valida con
                          una expresión estricta y se pasa como argumento (nunca por shell).
  escuchando()          → sockets TCP en escucha y si están abiertos a toda la red
  vigilante             → cada 15 min barre la red local (nmap -sn + tabla ARP): dispositivo
                          nuevo = notificación. Latencia cada 5 min, velocidad cada 6 h.
  subnetting            → el entrenador vive en el navegador; aquí solo se guardan los aciertos.

Datos en redes_data.json (fuera de git: MACs de tu casa).
"""

import datetime
import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request

from status import log
import almacen

DATA_FILE   = os.path.expanduser(os.environ.get("REDES_DATA", "~/MiPanelControl/redes_data.json"))
OUI_FILE    = "/usr/share/nmap/nmap-mac-prefixes"
VELOCIDAD_URL = "https://speed.cloudflare.com/__down?bytes=10000000"   # 10 MB
_lock       = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)
_oui        = {}
RE_DESTINO  = re.compile(r"^(?!-)[A-Za-z0-9.:-]{1,253}$")


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    for k, v in (("dispositivos", {}), ("latencia", []), ("velocidad", []), ("subnetting", {})):
        d.setdefault(k, v)
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=None)

def _run(cmd: list, timeout: int = 40) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "⏱ Tardó demasiado y se cortó."
    except Exception as e:
        return f"⚠ {e}"


# ─── Calculadora ───────────────────────────────────────────────────────────────
def calcular(texto: str) -> dict:
    texto = texto.strip()
    try:
        iface = ipaddress.ip_interface(texto if "/" in texto else texto + ("/64" if ":" in texto else "/24"))
    except ValueError as e:
        return {"error": f"No entiendo «{texto}»: {e}"}
    red = iface.network
    if red.version == 4:
        hosts = red.num_addresses - 2 if red.prefixlen < 31 else red.num_addresses
        primera = red.network_address + (1 if red.prefixlen < 31 else 0)
        ultima = red.broadcast_address - (1 if red.prefixlen < 31 else 0)
        binario = lambda ip: ".".join(f"{o:08b}" for o in ip.packed)
        return {
            "version": 4, "ip": str(iface.ip), "prefijo": red.prefixlen, "red": str(red.network_address),
            "broadcast": str(red.broadcast_address), "primera": str(primera), "ultima": str(ultima),
            "hosts": hosts, "mascara": str(red.netmask), "wildcard": str(red.hostmask),
            "clase": "privada" if red.is_private else "pública",
            "bin_ip": binario(iface.ip), "bin_mascara": binario(red.netmask), "bin_red": binario(red.network_address),
        }
    return {
        "version": 6, "ip": str(iface.ip), "ip_completa": iface.ip.exploded, "prefijo": red.prefixlen,
        "red": str(red.network_address), "red_completa": red.network_address.exploded,
        "rango": f"{red.network_address} – {red.broadcast_address}",
        "direcciones": f"2^{128 - red.prefixlen}",
        "tipo": ("documentación (2001:db8::/32)" if iface.ip in ipaddress.ip_network("2001:db8::/32")
                 else "enlace local (fe80::/10)" if iface.ip.is_link_local
                 else "única local (ULA, fc00::/7)" if iface.ip in ipaddress.ip_network("fc00::/7")
                 else "multicast (ff00::/8)" if iface.ip.is_multicast
                 else "global unicast (2000::/3)" if iface.ip in ipaddress.ip_network("2000::/3") else "especial"),
    }


# ─── Diagnóstico ───────────────────────────────────────────────────────────────
def diagnostico(tipo: str, destino: str) -> dict:
    destino = destino.strip()
    if not RE_DESTINO.match(destino):
        return {"error": "Destino no válido: escribe una IP o un nombre (p. ej. 8.8.8.8 o google.com)"}
    if tipo == "ping":
        salida = _run(["ping", "-c", "4", "-W", "2", destino], 20)
    elif tipo == "mtr":
        salida = _run(["mtr", "--report", "--report-cycles", "5", "--no-dns", destino], 60)
    elif tipo == "traceroute":
        salida = _run(["traceroute", "-n", "-w", "2", "-q", "1", "-m", "20", destino], 60)
    elif tipo == "dns":
        partes = []
        for rr in ("A", "AAAA", "MX", "NS", "TXT"):
            r = _run(["dig", "+short", "+time=3", "+tries=1", destino, rr], 10)
            if r:
                partes.append(f"{rr:5} {r.replace(chr(10), chr(10) + ' ' * 6)}")
        salida = "\n".join(partes) or "Sin respuesta (¿existe el nombre?)"
    else:
        return {"error": "Herramienta desconocida"}
    return {"salida": salida}

def escuchando() -> list:
    salida = _run(["ss", "-tlnpH"], 10)
    puertos = {}
    for linea in salida.splitlines():
        campos = linea.split()
        if len(campos) < 4:
            continue
        local = campos[3]
        direc, _, puerto = local.rpartition(":")
        proceso = re.search(r'users:\(\("([^"]+)"', linea)
        abierto = direc in ("0.0.0.0", "*", "[::]", "")
        solo_local = direc.startswith("127.") or direc in ("[::1]",)
        clave = (puerto, proceso.group(1) if proceso else "")
        p = puertos.setdefault(clave, {"puerto": int(puerto) if puerto.isdigit() else puerto,
                                        "proceso": clave[1] or "(otro usuario)", "direcciones": [],
                                        "alcance": "local"})
        p["direcciones"].append(direc)
        if abierto:
            p["alcance"] = "toda la red"
        elif not solo_local and p["alcance"] == "local":
            p["alcance"] = "una interfaz"
    orden = {"toda la red": 0, "una interfaz": 1, "local": 2}
    return sorted(puertos.values(), key=lambda p: (orden[p["alcance"]], str(p["puerto"])))


# ─── Vigilante de la red local ─────────────────────────────────────────────────
def _red_local() -> tuple:
    """(interfaz, red) de la ruta por defecto con menor métrica."""
    salida = _run(["ip", "-4", "route", "show", "default"], 5)
    mejor = None
    for l in salida.splitlines():
        m = re.search(r"dev (\S+).*?(?:metric (\d+))?$", l)
        if m and (mejor is None or int(m.group(2) or 0) < mejor[1]):
            mejor = (m.group(1), int(m.group(2) or 0))
    if not mejor:
        return None, None
    addr = _run(["ip", "-4", "-o", "addr", "show", "dev", mejor[0]], 5)
    m = re.search(r"inet (\S+)", addr)
    return (mejor[0], str(ipaddress.ip_interface(m.group(1)).network)) if m else (mejor[0], None)

def _fabricante(mac: str) -> str:
    # bit «administrada localmente»: los móviles modernos inventan una MAC por red (privacidad)
    if len(mac) > 1 and mac[1].lower() in "26ae":
        return "MAC aleatoria (móvil o portátil con privacidad)"
    if not _oui and os.path.isfile(OUI_FILE):
        with open(OUI_FILE, encoding="utf-8", errors="replace") as f:
            for l in f:
                if len(l) > 7 and not l.startswith("#"):
                    _oui[l[:6].upper()] = l[7:].strip()
    return _oui.get(mac.replace(":", "").upper()[:6], "")

def escanear() -> dict:
    iface, red = _red_local()
    if not red:
        return {"error": "No encuentro la red local"}
    salida = _run(["nmap", "-sn", "-T4", red], 120)
    vistos = {}
    for bloque in salida.split("Nmap scan report for ")[1:]:
        cab = bloque.splitlines()[0]
        m = re.match(r"(.+?) \((\d+\.\d+\.\d+\.\d+)\)", cab)
        nombre, ip = (m.group(1), m.group(2)) if m else ("", cab.strip())
        vistos[ip] = {"ip": ip, "hostname": nombre}
    # la tabla ARP da las MAC (nmap sin root no las ve)
    for l in _run(["ip", "neigh", "show", "dev", iface], 5).splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+) lladdr (\S+) (\S+)", l)
        if m and m.group(3) in ("REACHABLE", "STALE", "DELAY", "PERMANENT"):
            vistos.setdefault(m.group(1), {"ip": m.group(1), "hostname": ""})["mac"] = m.group(2).lower()
    # todas las IP de este equipo (cable y WiFi en la misma red cuentan como «este equipo»)
    propias = set(re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", _run(["ip", "-4", "-o", "addr", "show"], 5)))

    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        disp = d["dispositivos"]
        primera_vez = not disp
        ahora = datetime.datetime.now().isoformat(timespec="minutes")
        nuevos = []
        for v in vistos.values():
            clave = v.get("mac") or ("ip:" + v["ip"])
            e = disp.get(clave)
            if not e:
                e = disp[clave] = {"clave": clave, "mac": v.get("mac", ""), "nombre": "", "primera": ahora,
                                   "conocido": primera_vez or v["ip"] in propias,
                                   "fabricante": _fabricante(v.get("mac", "")) if v.get("mac") else ""}
                if not e["conocido"]:
                    nuevos.append(e)
            e.update({"ip": v["ip"], "hostname": v["hostname"] or e.get("hostname", ""), "ultima": ahora,
                      "propio": v["ip"] in propias})
        for e in disp.values():
            e["online"] = e.get("ultima") == ahora
        d["ultimo_escaneo"] = {"fecha": ahora, "red": red, "interfaz": iface, "encontrados": len(vistos)}
        _save(d)
    if nuevos:
        texto = ", ".join(f"{n['ip']} ({n['fabricante'] or n.get('hostname') or 'desconocido'})" for n in nuevos)
        log(f"🌐 Dispositivo nuevo en tu red: {texto}")
        try:
            from plyer import notification as _n
            _n.notify(title="🌐 Dispositivo nuevo en tu red", message=texto[:240], timeout=10)
        except Exception:
            pass
    return d["ultimo_escaneo"]

@_exclusivo
def marcar(clave: str, nombre: str = None, conocido: bool = None) -> bool:
    d = _load()
    e = d["dispositivos"].get(clave)
    if not e:
        return False
    if nombre is not None:
        e["nombre"] = nombre.strip()[:40]
    if conocido is not None:
        e["conocido"] = bool(conocido)
    _save(d)
    return True

def _medir_latencia():
    iface, _ = _red_local()
    gw = re.search(r"default via (\S+)", _run(["ip", "-4", "route", "show", "default"], 5))
    punto = {"t": datetime.datetime.now().isoformat(timespec="minutes")}
    for nombre, destino in (("router", gw.group(1) if gw else None), ("internet", "1.1.1.1")):
        if not destino:
            continue
        salida = _run(["ping", "-c", "3", "-W", "2", "-q", destino], 15)
        m = re.search(r"= [\d.]+/([\d.]+)/", salida)
        perdida = re.search(r"(\d+)% packet loss", salida)
        punto[nombre] = float(m.group(1)) if m else None
        punto[nombre + "_perdida"] = int(perdida.group(1)) if perdida else 100
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        d["latencia"] = (d["latencia"] + [punto])[-288:]   # 24 h a 1 cada 5 min
        _save(d)

def medir_velocidad() -> dict:
    t0 = time.time()
    try:
        with urllib.request.urlopen(VELOCIDAD_URL, timeout=60) as r:
            n = len(r.read())
        mbps = round(n * 8 / (time.time() - t0) / 1e6, 1)
    except Exception as e:
        return {"error": str(e)[:120]}
    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        d = _load()
        d["velocidad"] = (d["velocidad"] + [{"t": datetime.datetime.now().isoformat(timespec="minutes"),
                                             "mbps": mbps}])[-120:]
        _save(d)
    return {"mbps": mbps}

def _bucle():
    time.sleep(60)
    ciclo = 0
    while True:
        try:
            _medir_latencia()
            if ciclo % 3 == 0:
                escanear()
            if ciclo % 72 == 0:
                medir_velocidad()
        except Exception as e:
            log(f"⚠ Vigilante de red: {e}")
        ciclo += 1
        time.sleep(300)

def start_vigilante():
    threading.Thread(target=_bucle, daemon=True).start()


# ─── Datos para la pestaña ─────────────────────────────────────────────────────
@_exclusivo
def registrar_subnetting(tipo: str, acierto: bool):
    d = _load()
    s = d["subnetting"]
    t = s.setdefault("tipos", {}).setdefault(tipo[:20], {"v": 0, "f": 0})
    t["v" if acierto else "f"] += 1
    hoy = datetime.date.today().isoformat()
    s.setdefault("dias", {})[hoy] = s["dias"].get(hoy, 0) + 1
    s["racha_aciertos"] = s.get("racha_aciertos", 0) + 1 if acierto else 0
    s["mejor_racha"] = max(s.get("mejor_racha", 0), s["racha_aciertos"])
    _save(d)

def get_data() -> dict:
    d = _load()
    disp = sorted(d["dispositivos"].values(),
                  key=lambda e: (not e.get("online"), e.get("conocido", True), tuple(int(x) for x in e.get("ip", "0.0.0.0").split("."))))
    lat = d["latencia"]
    ultimas = [p for p in lat if p.get("internet") is not None][-12:]
    return {"dispositivos": disp, "ultimo_escaneo": d.get("ultimo_escaneo"),
            "latencia": lat[-288:], "velocidad": d["velocidad"][-30:],
            "latencia_media": round(sum(p["internet"] for p in ultimas) / len(ultimas), 1) if ultimas else None,
            "subnetting": d["subnetting"], "hoy": datetime.date.today().isoformat()}
