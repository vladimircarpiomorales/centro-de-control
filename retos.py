"""
Centro de Control PRO — retos.py
El reto de laboratorio del día, ELEGIDO (no inventado) entre lo que ya tienes:

  · CCNA   — fichas de labs de CML (~/Proyectos/ccna-labs/labs/*.html)
  · Linux  — retos con comprobación de la app de Certificaciones (src/<curso>/retos/*.json)
  · Azure  — labs oficiales del AZ-104 (az104-2026/build/labs/LAB_*.md)

Cómo se elige: cada día toca un área por turno (más AZ-104 si su examen está en
la agenda a menos de 60 días). Dentro del área, pesan más los temas que fallas:
los test de Certificaciones/AZ-104 y el entrenador de subnetting. Nunca repite
uno hecho. Se puede pedir otro. Datos en retos_data.json (fuera de git).
"""

import datetime
import glob
import json
import os
import random
import re
import almacen
import threading

PROYECTOS = os.path.expanduser(os.environ.get("PROYECTOS_DIR", "~/Proyectos"))
DATA_FILE = os.path.expanduser(os.environ.get("RETOS_DATA", "~/MiPanelControl/retos_data.json"))
_lock     = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)

AZ_TEMAS = {   # palabras de los módulos de los test → labs oficiales
    "rbac": ["LAB_02a"], "identit": ["LAB_01"], "entra": ["LAB_01"], "polic": ["LAB_02b"], "govern": ["LAB_02b"],
    "template": ["LAB_03b"], "arm": ["LAB_03b"], "bicep": ["LAB_03b"], "network": ["LAB_04", "LAB_05", "LAB_06"],
    "vnet": ["LAB_04", "LAB_05"], "dns": ["LAB_04"], "peering": ["LAB_05"], "load-balanc": ["LAB_06"],
    "storage": ["LAB_07"], "blob": ["LAB_07"], "virtual-machine": ["LAB_08"], "vm": ["LAB_08"],
    "web-app": ["LAB_09a"], "app-service": ["LAB_09a"], "container": ["LAB_09b", "LAB_09c"],
    "backup": ["LAB_10"], "recovery": ["LAB_10"], "monitor": ["LAB_11"],
}


def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("hechos", {})
    d.setdefault("dias", {})
    return d

def _save(d: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, d, indent=1)

SIGLAS = {"acl", "acls", "ip", "ipv4", "ipv6", "ssh", "vlan", "vlans", "ospf", "ospfv2", "ospfv3", "nat", "pat", "dhcp",
          "roas", "cli", "stp", "rstp", "hsrp", "fhrp", "eui", "dns", "ntp", "snmp", "arm", "rbac", "id", "vm", "vms",
          "lldp", "cdp", "wlan", "wlc", "aaa", "vty", "ios", "l2", "l3", "qos", "lacp", "ccna"}
NOMBRES = {"entra": "Entra", "azure": "Azure", "telnet": "Telnet", "etherchannel": "EtherChannel"}

def _bonito(slug: str) -> str:
    palabras = re.sub(r"\s+", " ", slug.replace("-", " ").replace("_", " ")).strip().split(" ")
    def palabra(p):
        l = p.lower()
        if l in SIGLAS:
            return l[:-1].upper() + "s" if l.endswith("s") and l[:-1] in SIGLAS else l.upper()
        return NOMBRES.get(l, l)
    salida = [palabra(p) for p in palabras if p]
    texto = " ".join(salida)
    return texto[:1].upper() + texto[1:]


# ─── Catálogo ──────────────────────────────────────────────────────────────────
def catalogo() -> list:
    retos = []
    for f in sorted(glob.glob(os.path.join(PROYECTOS, "ccna-labs", "labs", "*.html"))):
        slug = os.path.basename(f)[:-5]
        tema = re.sub(r"^(cs|free|prep|d\d)-[\d.]*-?", "", slug)
        retos.append({"id": "ccna:" + slug, "area": "ccna", "titulo": _bonito(re.sub(r"-\d+$", "", tema)) or slug,
                      "tema": tema, "donde": "CML (ficha de lab)", "ruta": f})
    for f in sorted(glob.glob(os.path.join(PROYECTOS, "lpi-2026", "src", "*", "retos", "*.json"))):
        curso = f.split(os.sep)[-3]
        try:
            lista = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for r in lista if isinstance(lista, list) else []:
            if not isinstance(r, dict) or not r.get("id"):
                continue
            retos.append({"id": "linux:" + r["id"], "area": "linux", "titulo": r.get("titulo", r["id"]),
                          "tema": os.path.basename(f)[:-5], "curso": curso, "donde": f"VM {r.get('distro', 'debian')} · {curso}",
                          "enunciado": r.get("enunciado", ""), "pista": r.get("pista", "")})
    for f in sorted(glob.glob(os.path.join(PROYECTOS, "az104-2026", "build", "labs", "LAB_*.md"))):
        nombre = os.path.basename(f)[:-3]
        clave = re.match(r"LAB_\d+[a-z]?", nombre).group(0)
        retos.append({"id": "azure:" + clave, "area": "azure", "titulo": _bonito(re.sub(r"^LAB_\w+?[-_]", "", nombre).replace("_", " ")),
                      "tema": clave, "donde": "Azure (suscripción de estudio)", "ruta": f})
    return retos


# ─── Debilidades ───────────────────────────────────────────────────────────────
def _test_fallos(ruta: str) -> dict:
    """{clave_de_pregunta: (aciertos, fallos)} de un fichero de progreso de las plataformas."""
    try:
        with open(ruta, encoding="utf-8") as f:
            t = json.load(f).get("test", {})
        return {k: (int(x.get("v", 0)), int(x.get("f", 0))) for k, x in t.items() if isinstance(x, dict)}
    except Exception:
        return {}

def debilidades() -> dict:
    """Peso extra (≥1) por tema, con el motivo."""
    pesos, motivos = {}, {}
    import estudio
    # Linux: cursos y temas con más fallos
    for ruta in glob.glob(os.path.join(estudio.DATOS_DIR, "lpi-*-progreso.json")):
        curso = os.path.basename(ruta)[len("lpi-"):-len("-progreso.json")]
        t = _test_fallos(ruta)
        v, f = sum(a for a, _ in t.values()), sum(b for _, b in t.values())
        if v + f >= 5 and f / (v + f) > 0.3:
            pesos["linux-curso:" + curso] = 1 + 3 * f / (v + f)
            motivos["linux-curso:" + curso] = f"en el test de {curso} fallas el {round(100 * f / (v + f))} %"
        for k, (a, b) in t.items():
            for tema in re.findall(r"[a-z]{4,}", k.split("-", 1)[-1]):
                pesos["linux-tema:" + tema] = pesos.get("linux-tema:" + tema, 1) + b * 0.5
    # Azure: módulos con fallos → labs
    for k, (a, b) in _test_fallos(estudio.AZ_PROGRESO).items():
        for palabra, labs in AZ_TEMAS.items():
            if b and palabra in k.lower():
                for lab in labs:
                    pesos["azure:" + lab] = pesos.get("azure:" + lab, 1) + b
                    motivos["azure:" + lab] = f"fallas preguntas de «{palabra}» en el AZ-104"
    # CCNA: entrenador de subnetting
    try:
        import redes
        tipos = redes._load()["subnetting"].get("tipos", {})
        for nombre, grupo, palabras in (("IPv4", lambda k: not k.startswith("ipv6"), ["ipv4", "subnet", "address"]),
                                        ("IPv6", lambda k: k.startswith("ipv6"), ["ipv6"])):
            v = sum(t["v"] for k, t in tipos.items() if grupo(k))
            f = sum(t["f"] for k, t in tipos.items() if grupo(k))
            if v + f >= 5 and f / (v + f) > 0.25:
                for p in palabras:
                    pesos["ccna-tema:" + p] = 1 + 4 * f / (v + f)
                    motivos["ccna-tema:" + p] = f"en el entrenador fallas el {round(100 * f / (v + f))} % de {nombre}"
    except Exception:
        pass
    return {"pesos": pesos, "motivos": motivos}

def _peso(r: dict, deb: dict) -> tuple:
    p, m = deb["pesos"], deb["motivos"]
    if r["area"] == "linux":
        w = p.get("linux-curso:" + r["curso"], 1) * p.get("linux-tema:" + r["tema"], 1)
        return w, m.get("linux-curso:" + r["curso"], "")
    if r["area"] == "azure":
        return p.get(r["id"], 1), m.get(r["id"], "")
    for clave in ("ccna-tema:ipv6", "ccna-tema:ipv4", "ccna-tema:subnet", "ccna-tema:address"):
        if clave.split(":")[1] in r["tema"]:
            return p.get(clave, 1), m.get(clave, "")
    return 1, ""


# ─── Reto del día ──────────────────────────────────────────────────────────────
def _area_del_dia(hoy: datetime.date) -> str:
    try:
        import agenda
        for e in agenda.get_data()["eventos"]:
            if e["tipo"] == "examen" and "az" in e["titulo"].lower() and 0 <= e["dias"] <= 60:
                return "azure" if hoy.toordinal() % 2 == 0 else ["linux", "ccna"][hoy.toordinal() // 2 % 2]
    except Exception:
        pass
    return ["ccna", "linux", "azure"][hoy.toordinal() % 3]

def _elegir(area: str, excluir: set) -> dict:
    deb = debilidades()
    candidatos = [r for r in catalogo() if r["area"] == area and r["id"] not in excluir]
    if not candidatos:
        candidatos = [r for r in catalogo() if r["id"] not in excluir]
    if not candidatos:
        return {}
    pesos = [_peso(r, deb) for r in candidatos]
    r = random.choices(candidatos, weights=[w for w, _ in pesos])[0]
    return {**r, "motivo": pesos[candidatos.index(r)][1]}

@_exclusivo
def del_dia(otro: bool = False) -> dict:
    d = _load()
    hoy = datetime.date.today().isoformat()
    actual = d["dias"].get(hoy)
    if actual and not otro:
        reto = next((r for r in catalogo() if r["id"] == actual["id"]), None)
        if reto:
            return {**reto, "motivo": actual.get("motivo", ""), "hecho": actual["id"] in d["hechos"]}
    excluir = set(d["hechos"]) | ({actual["id"]} if actual else set())
    area = _area_del_dia(datetime.date.today())
    if otro and actual:   # «otro»: rota de área para variar
        area = {"ccna": "linux", "linux": "azure", "azure": "ccna"}[actual.get("area", "ccna")]
    reto = _elegir(area, excluir)
    if reto:
        d["dias"] = {**{k: v for k, v in d["dias"].items() if k >= (datetime.date.today() - datetime.timedelta(days=60)).isoformat()},
                     hoy: {"id": reto["id"], "area": reto["area"], "motivo": reto["motivo"]}}
        _save(d)
    return {**reto, "hecho": False}

@_exclusivo
def marcar_hecho(rid: str) -> bool:
    if rid not in {r["id"] for r in catalogo()}:
        return False
    d = _load()
    d["hechos"][rid] = datetime.date.today().isoformat()
    _save(d)
    return True

def ruta_de(rid: str) -> str:
    """Solo rutas del catálogo (para abrir la ficha o leer el lab)."""
    return next((r.get("ruta", "") for r in catalogo() if r["id"] == rid), "")

def resumen() -> dict:
    d = _load()
    cat = catalogo()
    por_area = {a: sum(1 for r in cat if r["area"] == a) for a in ("ccna", "linux", "azure")}
    hechos = {a: sum(1 for h in d["hechos"] if h.startswith(a + ":")) for a in por_area}
    return {"total": por_area, "hechos": hechos,
            "semana": sum(1 for f in d["hechos"].values()
                          if f >= (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat())}
