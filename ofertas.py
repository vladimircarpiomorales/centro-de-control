"""
Centro de Control PRO — ofertas.py
Buscador de ofertas de empleo en Madrid + registro de candidaturas.

Idea y lectores de portales tomados de ai-job-search (MadsLorentzen, MIT) y de su
fork español ai-job-search-spain (erikpr1994): mismas URLs públicas y mismos
"ganchos" HTML, portados a Python sin dependencias.

Fuentes (todas sin cuenta, volumen bajo y con pausas — uso personal):
  1. InfoJobs     — listado server-side (5 tarjetas por consulta), provincia Madrid
  2. Tecnoempleo  — listado plano, provincia Madrid (pr=,263,)
  3. LinkedIn     — endpoint público jobs-guest, Madrid + remoto en España

Flujo: refresco cada 12 h → relevancia por palabras clave (gratis, al instante) →
«Evaluar con IA» lee la oferta completa y la puntúa con Ollama según el marco de
evaluación del repo original (técnico, experiencia, carrera, idioma, ubicación) →
registro de estados (guardada, postulada, entrevista…) con aviso de seguimiento
a los 10 días sin respuesta. Persistencia en ofertas_data.json.
"""

import datetime
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.parse
from collections import Counter

from extensions import socketio
from status import log
from rag import _ollama_post, _json_ollama
from becas import _http_get
import almacen
import perfil

DATA_FILE        = os.path.expanduser(os.environ.get("OFERTAS_DATA", "~/MiPanelControl/ofertas_data.json"))
REFRESH_INTERVAL = 5 * 3600    # cada 5 h: así cae varias veces al día y no solo de noche
PAUSA            = 5      # segundos entre peticiones a un mismo portal
PAUSA_LINKEDIN   = 8
DIAS_SEGUIMIENTO = 10
DIAS_RETENCION   = 30     # ofertas sin tocar que ya no aparecen se borran a los 30 días
META_SEMANAL     = 10     # «Postular a 10 ofertas por semana» (plan de carrera, fase 1)
MODELO_DEFAULT   = "qwen3.5:4b"   # cabe en los 4 GB de la T1200: 2,5× más rápido que qwen2.5:7b y sin inventar
_lock            = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)
_refrescando     = threading.Lock()

CONFIG_SEED = {
    "consultas": [
        "administrador de sistemas",
        "técnico de sistemas",
        "técnico de redes",
        "técnico soporte informático",
        "azure",
        "infraestructura IT",
    ],
    # LinkedIn en remoto (toda España) solo para estas, para no duplicar volumen
    "consultas_remoto": ["administrador de sistemas", "azure"],
    "linkedin_ubicacion": "Madrid, Community of Madrid, Spain",
    # El perfil de Mi Carrera habla sobre todo de redes; sin esto la IA cree que no
    # sabe Linux ni Windows. Sale de perfil.json → competencias; editable en ofertas_data.json → config.competencias.
    "competencias": perfil.get().get("competencias", ""),
}

ESTADOS = ["guardada", "postulada", "entrevista", "oferta", "rechazada", "descartada"]


# ─── Utilidades ────────────────────────────────────────────────────────────────
def _clean(fragmento: str) -> str:
    texto = html.unescape(re.sub(r"<[^>]+>", " ", fragmento or ""))
    return re.sub(r"\s+", " ", texto).strip()

def _texto_largo(fragmento: str) -> str:
    """Como _clean pero respetando párrafos y listas (para descripciones)."""
    f = re.sub(r"<\s*br\s*/?>", "\n", fragmento or "", flags=re.I)
    f = re.sub(r"</(p|li|ul|ol|div|h\d)>", "\n", f, flags=re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", f))
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n\n", texto).strip()

def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def _hoy() -> str:
    return datetime.date.today().isoformat()

def _emit(evento: str, payload: dict):
    try:
        socketio.emit(evento, payload)
    except Exception:
        pass

def _abs(url: str, base: str) -> str:
    url = html.unescape(url).strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return base + url
    return url


# ─── Lectores de portales ──────────────────────────────────────────────────────
def _infojobs(consulta: str) -> list:
    qs = urllib.parse.urlencode({"keyword": consulta, "provinceIds": "33",
                                 "sinceDate": "_15_DAYS", "sortBy": "PUBLICATION_DATE"})
    pagina = _http_get("https://www.infojobs.net/jobsearch/search-results/list.xhtml?" + qs, timeout=15)
    # InfoJobs a veces sirve un captcha en vez del listado: que se sepa, no un 0 mudo
    if 'id="job-title-' not in pagina and re.search(r"captcha", pagina, re.I):
        raise RuntimeError("InfoJobs ha pedido captcha (pasa a ratos; se reintenta en la próxima búsqueda)")
    items = []
    # cada oferta real tiene un ancla id="job-title-<hex>"; los banners no
    for trozo in pagina.split('id="job-title-')[1:]:
        m = re.match(r"([0-9a-f]+)\"", trozo, re.I)
        if not m:
            continue
        link = re.search(r'class="ij-OfferCardContent-description-link[^"]*"[^>]*href="([^"]+)"', trozo)
        tit  = re.search(r'class="ij-OfferCardContent-description-title-link"[^>]*>([\s\S]*?)</span>', trozo)
        emp  = re.search(r'class="ij-OfferCardContent-description-subtitle"[^>]*>([\s\S]*?)</h3>', trozo)
        loc  = re.search(r'class="ij-OfferCardContent-description-list-item-truncate"[^>]*>([\s\S]*?)</span>', trozo)
        fec  = re.search(r'class="ij-FormatterSincedate[^"]*"[^>]*>([\s\S]*?)</span>', trozo)
        titulo = _clean(tit.group(1)) if tit else ""
        if not titulo:
            continue
        modalidad = ""
        for li in re.findall(r'class="ij-OfferCardContent-description-list-item"[^>]*>([\s\S]*?)</li>', trozo):
            t = _clean(li)
            if re.search(r"presencial|h[ií]brido|teletrabajo|remoto", t, re.I):
                modalidad = t
                break
        url = _abs(link.group(1), "https://www.infojobs.net").split("?")[0] if link \
            else f"https://www.infojobs.net/empleo/empleo/of-i{m.group(1)}"
        items.append({"fuente": "infojobs", "nid": m.group(1).lower(), "titulo": titulo,
                      "empresa": _clean(emp.group(1)) if emp else "",
                      "ubicacion": _clean(loc.group(1)) if loc else "",
                      "modalidad": modalidad, "publicada": _clean(fec.group(1)) if fec else "",
                      "url": url})
    return items

def _tecnoempleo(consulta: str) -> list:
    qs = urllib.parse.urlencode({"te": consulta, "pr": ",263,"})
    pagina = _http_get("https://www.tecnoempleo.com/ofertas-trabajo/?" + qs, timeout=15)
    items = []
    for trozo in pagina.split('<a name="rf-')[1:]:
        m = re.match(r"([0-9a-fA-F]+)\"", trozo)
        if not m:
            continue
        url = re.search(r"onclick=\"location\.href='([^']+)'\"", trozo) or \
              re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"', trozo, re.I)
        tit = re.search(r'<h3[^>]*>\s*<a[^>]+title="([^"]+)"', trozo, re.I)
        titulo = html.unescape(tit.group(1)).strip() if tit else ""
        if not titulo:
            continue
        emp = re.search(r'<a title="Ofertas de Empleo ([^"]*)"', trozo, re.I)
        ubic, modalidad, fecha = "", "", ""
        span = re.search(r'<span class="d-block d-lg-none[^"]*"[^>]*>([\s\S]*?)</span>', trozo, re.I)
        if span:
            s = span.group(1)
            b = re.search(r"<b>([^<]+)</b>", s)
            ubic = html.unescape(b.group(1)).strip() if b else ""
            p = re.search(r"\(([^)]+)\)", s)
            modalidad = html.unescape(p.group(1)).strip() if p else ""
            if re.search("remoto", ubic, re.I) and not modalidad:
                modalidad, ubic = ubic, ""
            d = re.search(r"(\d{2}/\d{2}/\d{4})", s)
            fecha = d.group(1) if d else ""
        items.append({"fuente": "tecnoempleo", "nid": m.group(1), "titulo": titulo,
                      "empresa": html.unescape(emp.group(1)).strip() if emp else "",
                      "ubicacion": ubic, "modalidad": modalidad, "publicada": fecha,
                      "url": html.unescape(url.group(1)) if url else
                             f"https://www.tecnoempleo.com/oferta-trabajo/rf-{m.group(1)}"})
    return items

def _linkedin(consulta: str, ubicacion: str, remoto: bool = False) -> list:
    params = {"keywords": consulta, "location": ubicacion, "f_TPR": "r604800", "start": "0"}
    if remoto:
        params["f_WT"] = "2"
    pagina = _http_get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                       + urllib.parse.urlencode(params), timeout=15)
    items = []
    for trozo in pagina.split('data-entity-urn="urn:li:jobPosting:')[1:]:
        m = re.match(r"(\d+)", trozo)
        if not m:
            continue
        tit = re.search(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', trozo)
        titulo = _clean(tit.group(1)) if tit else ""
        if not titulo:
            continue
        emp = re.search(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', trozo)
        loc = re.search(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', trozo)
        fec = re.search(r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', trozo)
        lugar = _clean(loc.group(1)) if loc else ""
        # f_WT=2 no es fiable: cuela ofertas presenciales con sede en Madrid. Con
        # sede en Madrid no se sabe la modalidad; fuera de Madrid, si sale en la
        # búsqueda remota, es que lo es (si no, no se buscaría allí).
        items.append({"fuente": "linkedin", "nid": m.group(1), "titulo": titulo,
                      "empresa": _clean(emp.group(1)) if emp else "",
                      "ubicacion": lugar,
                      "modalidad": "remoto" if remoto and not _MADRID.search(lugar) else "",
                      "publicada": fec.group(1) if fec else "",
                      "url": f"https://www.linkedin.com/jobs/view/{m.group(1)}"})
    return items


def _descripcion(it: dict) -> str:
    """Descarga el texto completo de una oferta (solo al evaluarla, una a una)."""
    fuente = it.get("fuente")
    if fuente == "linkedin":
        pagina = _http_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{it['nid']}", timeout=15)
        m = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>([\s\S]*?)</div>', pagina) or \
            re.search(r'class="description__text[^"]*"[^>]*>([\s\S]*?)</section>', pagina)
        return _texto_largo(m.group(1)) if m else ""
    pagina = _http_get(it["url"], timeout=15)
    if fuente == "infojobs":
        # el detalle de InfoJobs suele devolver un captcha a peticiones automáticas
        if re.search(r"captcha", pagina, re.I) and "Descripci" not in pagina:
            raise RuntimeError("InfoJobs pide captcha para ver el detalle; pega el texto de la oferta")
        m = re.search(r"Descripci[oó]n</h3>([\s\S]*?)</article>", pagina, re.I)
        extra = [_clean(x) for x in re.findall(
            r'class="[^"]*ij-OfferDetailHeader-detailsList-item[^"]*"[^>]*>[\s\S]*?<p[^>]*>([\s\S]*?)</p>', pagina)]
        cuerpo = _texto_largo(m.group(1)) if m else ""
        return ("Datos: " + " · ".join(x for x in extra if x) + "\n\n" if extra else "") + cuerpo
    if fuente == "tecnoempleo":
        for bloque in re.findall(r'<script[^>]+application/ld\+json[^>]*>([\s\S]*?)</script>', pagina, re.I):
            try:
                ld = json.loads(bloque)
            except Exception:
                continue
            for nodo in ld if isinstance(ld, list) else [ld]:
                if isinstance(nodo, dict) and nodo.get("@type") == "JobPosting" and nodo.get("description"):
                    return _texto_largo(nodo["description"])
        return ""
    return _texto_largo(pagina)[:4000]


# ─── Relevancia rápida (sin IA) ────────────────────────────────────────────────
# Pesos pensados para su perfil: redes + sistemas + Azure, sin desarrollo ni senior.
_POSITIVAS = {
    "sistemas": 18, "redes": 18, "network": 14, "linux": 12, "windows": 8, "azure": 16,
    "cloud": 10, "soporte": 10, "helpdesk": 8, "help desk": 8, "service desk": 8,
    "microinformatica": 8, "noc": 10, "infraestructura": 14, "aruba": 18, "cisco": 14,
    "vmware": 10, "office 365": 8, "microsoft 365": 8, "active directory": 10,
    "administrador": 8, "tecnico": 8, "it": 4, "junior": 6, "wifi": 10, "comunicaciones": 8,
}
_NEGATIVAS = {
    "senior": -12, "sr ": -10, "lead": -12, "jefe": -12, "head of": -15, "director": -20,
    "arquitecto": -10, "architect": -10, "desarrollador": -20, "developer": -20,
    "programador": -20, "java": -15, ".net": -15, "frontend": -20, "backend": -15,
    "full stack": -20, "fullstack": -20, "sap": -18, "abap": -20, "data scientist": -20,
    "comercial": -18, "ventas": -18, "sales": -18, "becario": -15, "practicas": -15,
    "internship": -15, "dba": -8, "salesforce": -18,
}
_IDIOMA = re.compile(r"\b(ingl[eé]s|english|bilingual|biling[uü]e|alem[aá]n|franc[eé]s|german|french)\b", re.I)

def _relevancia(it: dict) -> int:
    t = " " + _norm(it["titulo"]) + " "
    puntos = 20
    for k, v in _POSITIVAS.items():
        if " " + k + " " in t or (len(k) > 4 and k in t):
            puntos += v
    for k, v in _NEGATIVAS.items():
        if k in t:
            puntos += v
    return max(0, min(100, puntos))


# ─── Persistencia ──────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {"items": {}, "last_update": None}
    data.setdefault("items", {})
    cfg = data.setdefault("config", {})
    for k, v in CONFIG_SEED.items():
        cfg.setdefault(k, v)
    data.setdefault("errores", [])
    return data

def _save(data: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, data, indent=1)

def _make_id(fuente: str, nid: str) -> str:
    return hashlib.sha1(f"{fuente}:{nid}".encode()).hexdigest()[:12]

def _clave_dup(it: dict) -> str:
    return _norm(it["titulo"]) + "|" + _norm(it.get("empresa", ""))


# ─── Seguimiento y estadísticas ────────────────────────────────────────────────
def _ultimo_cambio(it: dict) -> str:
    h = it.get("historial") or []
    return h[-1]["fecha"] if h else it.get("first_seen", _hoy())

def _necesita_seguimiento(it: dict) -> bool:
    if it.get("estado") not in ("postulada", "entrevista"):
        return False
    dias = (datetime.date.today() - datetime.date.fromisoformat(_ultimo_cambio(it))).days
    return dias >= DIAS_SEGUIMIENTO

def _stats(items: list) -> dict:
    hoy    = datetime.date.today()
    lunes  = (hoy - datetime.timedelta(days=hoy.weekday())).isoformat()
    semana = sum(1 for it in items for h in it.get("historial", [])
                 if h["estado"] == "postulada" and h["fecha"] >= lunes and not h.get("seguimiento"))
    por_estado = Counter(it.get("estado") or "nueva" for it in items)
    carencias  = Counter()
    for it in items:
        if it.get("estado") == "descartada":
            continue
        for c in (it.get("eval") or {}).get("carencias", []):
            c = c.strip().rstrip(".")
            if c:
                carencias[c[:1].upper() + c[1:]] += 1
    return {
        "semana": semana, "meta_semana": META_SEMANAL,
        "por_estado": dict(por_estado),
        "nuevas": sum(1 for it in items if it.get("new") and not it.get("estado")),
        "seguimiento": sum(1 for it in items if it.get("seguimiento")),
        "brechas": carencias.most_common(10),
    }


# ─── API pública del motor ─────────────────────────────────────────────────────
def get_data() -> dict:
    data  = _load()
    items = list(data["items"].values())
    for it in items:
        it["seguimiento"] = _necesita_seguimiento(it)
    items.sort(key=lambda i: (
        i.get("estado") == "descartada",
        not i.get("seguimiento"),
        not i.get("new"),
        -((i.get("eval") or {}).get("encaje", -1)),
        -i.get("relevancia", 0),
    ))
    return {"items": items, "last_update": data["last_update"], "config": data["config"],
            "errores": data["errores"], "estados": ESTADOS, "stats": _stats(items),
            "refrescando": _refrescando.locked(), "fuentes_rotas": _fuentes_rotas()}

def _fuentes_rotas() -> list:
    try:
        import salud_fuentes
        return [f["etiqueta"] for k, f in salud_fuentes.estado().items() if k.startswith("ofertas:") and f["rota"]]
    except Exception:
        return []


def refresh() -> tuple:
    """Consulta los tres portales con pausas. Devuelve (total, nuevas)."""
    if not _refrescando.acquire(blocking=False):
        log("💼 Ya hay una búsqueda de ofertas en marcha")
        return 0, 0
    try:
        return _refresh()
    finally:
        _refrescando.release()

def _refresh() -> tuple:
    data   = _load()
    cfg    = data["config"]
    log("💼 Buscando ofertas de empleo en Madrid (InfoJobs, Tecnoempleo, LinkedIn)…")
    tareas = []
    for q in cfg["consultas"]:
        tareas.append(("InfoJobs", PAUSA, lambda q=q: _infojobs(q), q))
        tareas.append(("Tecnoempleo", PAUSA, lambda q=q: _tecnoempleo(q), q))
        tareas.append(("LinkedIn", PAUSA_LINKEDIN, lambda q=q: _linkedin(q, cfg["linkedin_ubicacion"]), q))
    for q in cfg.get("consultas_remoto", []):
        tareas.append(("LinkedIn remoto", PAUSA_LINKEDIN, lambda q=q: _linkedin(q, "Spain", remoto=True), q))

    encontrados, errores, por_fuente, captcha = [], [], Counter(), set()
    for nombre, pausa, fn, q in tareas:
        try:
            res = fn()
            encontrados.extend(res)
            por_fuente[nombre] += len(res)
        except Exception as e:
            errores.append(f"{nombre} «{q}»: {e}")
            if "captcha" in str(e).lower():
                captcha.add(nombre)
        time.sleep(pausa)
    for nombre, n in por_fuente.items():
        log(f"  💼 {nombre}: {n} tarjetas")
    # salud de los lectores: una fuente que falla o trae 0 cuenta como 0
    import salud_fuentes
    for nombre in dict.fromkeys(t[0] for t in tareas):
        salud_fuentes.registrar(f"ofertas:{nombre}", f"{nombre} (ofertas)", por_fuente.get(nombre, 0),
                                motivo="captcha" if nombre in captcha and not por_fuente.get(nombre) else None)
    for e in errores:
        log(f"  ⚠ {e}")

    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        data = _load()   # releer: la búsqueda tarda minutos y pueden haber cambiado estados o notas
        prev        = data["items"]
        primera_vez = not prev
        hoy         = _hoy()
        vistos      = set()
        por_clave   = {_clave_dup(v): k for k, v in prev.items()}
        nuevas      = 0

        for c in encontrados:
            oid = _make_id(c["fuente"], c["nid"])
            # la misma oferta publicada en dos portales: se queda la primera, se anota la otra
            dup = por_clave.get(_clave_dup(c))
            if oid not in prev and dup and dup != oid:
                otra = prev[dup]
                fuentes = otra.setdefault("tambien_en", [])
                if c["fuente"] != otra["fuente"] and not any(f["fuente"] == c["fuente"] for f in fuentes):
                    fuentes.append({"fuente": c["fuente"], "url": c["url"]})
                otra["last_seen"] = hoy
                vistos.add(dup)
                continue
            vistos.add(oid)
            if oid in prev:
                prev[oid].update({k: c[k] for k in ("titulo", "empresa", "ubicacion", "modalidad", "publicada", "url")})
                prev[oid]["last_seen"] = hoy
                continue
            c.update({"id": oid, "first_seen": hoy, "last_seen": hoy, "new": not primera_vez,
                      "relevancia": _relevancia(c), "idioma_titulo": bool(_IDIOMA.search(c["titulo"]))})
            prev[oid] = c
            por_clave[_clave_dup(c)] = oid
            if c["new"] and c["relevancia"] >= 40:
                nuevas += 1

        # limpieza: lo que nunca se tocó y lleva 30 días sin aparecer, fuera
        limite = (datetime.date.today() - datetime.timedelta(days=DIAS_RETENCION)).isoformat()
        for oid in list(prev):
            it = prev[oid]
            if oid in vistos or it.get("estado") not in (None, "descartada"):
                continue
            if it.get("last_seen", it.get("first_seen", hoy)) < limite:
                del prev[oid]

        data["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        data["errores"]     = errores
        _save(data)
    log(f"✅ Ofertas: {len(prev)} en el índice ({nuevas} nuevas relevantes)")
    _emit("ofertas_updated", {"total": len(prev), "nuevas": nuevas})
    return len(prev), nuevas


@_exclusivo
def set_estado(oid: str, estado: str) -> bool:
    if estado not in ESTADOS and estado != "":
        return False
    data = _load()
    it   = data["items"].get(oid)
    if not it:
        return False
    anterior = it.get("estado")
    it["estado"] = estado or None
    it["new"]    = False
    if estado and estado != anterior:
        it.setdefault("historial", []).append({"fecha": _hoy(), "estado": estado})
    _save(data)
    log(f"💼 {it['titulo'][:50]} → {estado or 'sin estado'}")
    # un paso real en la búsqueda también es un logro del plan de carrera
    if estado in ("entrevista", "oferta") and anterior != estado:
        try:
            import carrera
            que = "Conseguí entrevista" if estado == "entrevista" else "Recibí una oferta"
            carrera.add_logro(f"{que}: {it['titulo']}" + (f" en {it['empresa']}" if it.get("empresa") else ""))
        except Exception:
            pass
    return True

@_exclusivo
def set_nota(oid: str, nota: str) -> bool:
    data = _load()
    it   = data["items"].get(oid)
    if not it:
        return False
    it["nota"] = nota.strip()[:1000]
    _save(data)
    return True

@_exclusivo
def seguimiento_hecho(oid: str) -> bool:
    """Registra que se ha escrito para preguntar: reinicia el contador de 10 días."""
    data = _load()
    it   = data["items"].get(oid)
    if not it or it.get("estado") not in ("postulada", "entrevista"):
        return False
    it.setdefault("historial", []).append({"fecha": _hoy(), "estado": it["estado"], "seguimiento": True})
    _save(data)
    return True

@_exclusivo
def add_manual(titulo: str, empresa: str, url: str) -> bool:
    """Oferta encontrada por otra vía (web de la empresa, ETT, un contacto…)."""
    titulo = titulo.strip()
    if not titulo:
        return False
    data = _load()
    nid  = hashlib.md5((titulo + empresa + url + _hoy()).encode()).hexdigest()[:10]
    oid  = _make_id("manual", nid)
    data["items"][oid] = {"id": oid, "fuente": "manual", "nid": nid, "titulo": titulo,
                          "empresa": empresa.strip(), "ubicacion": "", "modalidad": "", "publicada": "",
                          "url": url.strip(), "first_seen": _hoy(), "last_seen": _hoy(), "new": False,
                          "relevancia": _relevancia({"titulo": titulo}), "estado": "guardada",
                          "historial": [{"fecha": _hoy(), "estado": "guardada"}]}
    _save(data)
    return True

@_exclusivo
def set_descripcion(oid: str, texto: str) -> bool:
    """Texto de la oferta pegado a mano (InfoJobs con captcha, ofertas manuales…)."""
    data = _load()
    it   = data["items"].get(oid)
    if not it or not texto.strip():
        return False
    it["descripcion"] = texto.strip()[:8000]
    _save(data)
    return True

@_exclusivo
def marcar_vistas():
    data = _load()
    for it in data["items"].values():
        it["new"] = False
    _save(data)


# ─── Evaluación con IA local ───────────────────────────────────────────────────
PROMPT_EVAL = (
    "Eres un orientador laboral experto en el mercado IT de Madrid. Evalúa si esta oferta "
    "encaja con el candidato. Sé honesto: ni le hundas ni le infles. Usa SOLO los datos de "
    "abajo. Si la descripción no está disponible, juzga solo por el título y deja "
    "«carencias» vacía: no inventes requisitos que la oferta no pide.\n\n"
    "Puntúa de 0 a 100:\n"
    "- tecnico: ¿sus habilidades cubren lo que piden? (80+ = lo central es su fuerte; "
    "40-59 = tendría que formarse bastante)\n"
    "- experiencia: ¿su trayectoria encaja por la FUNCIÓN real, no por el nombre del puesto?\n"
    "- carrera: ¿le acerca a su objetivo (Cloud/Infraestructura)? Un empleo de sistemas o redes "
    "que dé ingresos ya también cuenta como positivo en su situación.\n"
    "Además:\n"
    "- idioma: PASS si no piden idiomas o solo castellano; FLAG si piden inglés y su nivel (ver "
    "competencias) no llega, pero muchas empresas son flexibles: es un aviso, no un descarte); FAIL solo "
    "si exigen un idioma que NO habla en absoluto (alemán, francés, italiano…).\n"
    "- idioma_nota: si es FLAG o FAIL, copia literalmente lo que pide la oferta sobre idiomas.\n"
    "- fuertes: 2-3 cosas concretas de SU perfil que responden a algo que ESTA oferta pide.\n"
    "- carencias: 0-4 requisitos que la oferta pide EXPLÍCITAMENTE y él no cubre, cada uno "
    "en 1-4 palabras.\n"
    "- recomendacion: «postular», «postular con reservas» o «no postular».\n"
    "- resumen: 1-2 frases en español hablándole de tú, con el porqué.\n\n"
    "Responde SOLO con JSON con estas claves exactas: tecnico, experiencia, carrera, idioma, "
    "idioma_nota, fuertes, carencias, recomendacion, resumen.\n\n"
)

# Municipios de la Comunidad donde suele haber oficinas IT; cualquier otro sitio → aviso
_MADRID = re.compile(r"madrid|alcobendas|sanse|san sebasti[aá]n de los reyes|las rozas|pozuelo|"
                     r"tres cantos|getafe|legan[eé]s|alcal[aá]|majadahonda|boadilla|fuenlabrada|"
                     r"m[oó]stoles|torrej[oó]n|coslada|rivas|alcorc[oó]n|villaviciosa|"
                     r"san fernando de henares|arganda|parla|spain|espa[ñn]a|remot|teletrabajo", re.I)

def _encaje(ev: dict) -> int:
    """Nota global calculada aquí (no por el modelo) para que sea coherente con el
    desglose: media ponderada; el idioma resta como aviso y solo veta si es FAIL."""
    t, e, c = (ev.get(k) if ev.get(k) is not None else 50 for k in ("tecnico", "experiencia", "carrera"))
    nota = round(0.4 * t + 0.35 * e + 0.25 * c)
    if ev["idioma"] == "FLAG":
        nota -= 10
    if "FAIL" in (ev["idioma"], ev["ubicacion"]):
        nota = min(nota, 30)
    return max(0, min(100, nota))

def _perfil() -> str:
    try:
        import carrera
        d = carrera._load()
        comp = _load()["config"].get("competencias", "")
        return f"{d.get('perfil', '')}\nCompetencias técnicas: {comp}\nObjetivo: {d.get('meta', '')}"
    except Exception:
        return ""

def evaluar(oid: str, modelo: str = MODELO_DEFAULT):
    """Lee la oferta completa y la puntúa con Ollama. Corre en background (run_bg)."""
    data = _load()
    it   = data["items"].get(oid)
    if not it:
        return
    log(f"🧠 Evaluando «{it['titulo'][:50]}» con {modelo}…")
    try:
        desc = it.get("descripcion") or (_descripcion(it) if it["fuente"] != "manual" else "")
    except Exception as e:
        desc = ""
        log(f"  ⚠ No pude leer la oferta completa ({e}); evalúo solo con el título")
    oferta = (f"Puesto: {it['titulo']}\nEmpresa: {it.get('empresa') or '—'}\n"
              f"Ubicación: {it.get('ubicacion') or '—'} {it.get('modalidad') or ''}\n\n"
              f"Descripción:\n{desc[:5000] or '(no disponible)'}")
    try:
        r = _ollama_post("/api/chat", {
            "model": modelo, "format": "json", "stream": False, "think": False,
            "options": {"temperature": 0.2},
            "messages": [{"role": "user", "content":
                          PROMPT_EVAL + "CANDIDATO:\n" + _perfil() + "\n\nOFERTA:\n" + oferta}],
        }, timeout=420)
    except Exception as e:
        msg = ("⚠ No pude hablar con Ollama. Enciende «Ollama (motor IA)» en la pestaña "
               f"Locales y vuelve a intentarlo. ({e})")
        log(msg)
        _emit("ofertas_eval", {"id": oid, "error": msg})
        return
    try:
        ev = _json_ollama(r)
    except ValueError:
        msg = "⚠ El modelo contestó algo que no es JSON; vuelve a intentarlo"
        log(msg)
        _emit("ofertas_eval", {"id": oid, "error": msg})
        return

    def _num(v):
        try:
            return max(0, min(100, int(float(v))))
        except Exception:
            return None
    def _lista(v):
        return [str(x).strip().rstrip(".")[:70] for x in v if str(x).strip()][:4] if isinstance(v, list) else []
    idioma = str(ev.get("idioma", "")).upper()[:4]
    nota_idioma = str(ev.get("idioma_nota") or "")
    if nota_idioma.strip().lower() in ("none", "null", "n/a", "-"):
        nota_idioma = ""
    # llama3.1 a veces marca FAIL por inglés: el inglés es aviso (FLAG), no descarte
    if idioma == "FAIL" and not re.search(r"alem|franc|ital|portug|german|french|dutch|holand|chin|japon",
                                          nota_idioma + " " + desc, re.I):
        idioma = "FLAG"
    if idioma not in ("PASS", "FLAG", "FAIL"):
        idioma = "FLAG" if _IDIOMA.search(it["titulo"] + " " + desc) else "PASS"
    lugar = f"{it.get('ubicacion', '')} {it.get('modalidad', '')}"
    limpio = {
        "tecnico": _num(ev.get("tecnico")), "experiencia": _num(ev.get("experiencia")),
        "carrera": _num(ev.get("carrera")),
        "idioma": idioma, "idioma_nota": nota_idioma[:200],
        # la ubicación ya la sabemos por la tarjeta: no se le pregunta al modelo
        "ubicacion": "PASS" if (not lugar.strip() or _MADRID.search(lugar)) else "FLAG",
        "fuertes": _lista(ev.get("fuertes")),
        "carencias": _lista(ev.get("carencias")) if desc else [],
        "recomendacion": str(ev.get("recomendacion", ""))[:40], "resumen": str(ev.get("resumen", ""))[:600],
        "modelo": modelo, "fecha": _hoy(), "sin_descripcion": not desc,
    }
    limpio["encaje"] = _encaje(limpio)

    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        data = _load()  # recargar: la evaluación tarda y pueden haber cambiado estados
        if oid in data["items"]:
            data["items"][oid]["eval"] = limpio
            if desc:
                data["items"][oid]["descripcion"] = desc[:8000]
            _save(data)
    log(f"🧠 «{it['titulo'][:50]}»: encaje {limpio['encaje']}/100 — {limpio['recomendacion']}")
    _emit("ofertas_eval", {"id": oid, "eval": limpio})

def evaluar_lote(n: int = 8, modelo: str = MODELO_DEFAULT):
    """Evalúa las n ofertas sin evaluar más relevantes (como /rank del repo original)."""
    data = _load()
    pendientes = sorted(
        (it for it in data["items"].values()
         if not it.get("eval") and it.get("estado") != "descartada" and it.get("relevancia", 0) >= 40),
        key=lambda i: -i.get("relevancia", 0))[:n]
    if not pendientes:
        log("🧠 No hay ofertas relevantes pendientes de evaluar")
        return
    log(f"🧠 Evaluando {len(pendientes)} ofertas con {modelo} (una a una)…")
    for it in pendientes:
        evaluar(it["id"], modelo)
        time.sleep(PAUSA)

AUTO_EVAL = 15   # ofertas por tanda que la cola IA evalúa sola tras cada búsqueda

def encolar_evaluaciones(n: int = AUTO_EVAL):
    """Tras buscar, deja las mejores sin evaluar en la cola IA: cuando abras la
    pestaña ya tienen nota. Una por trabajo, para poder parar entre una y otra."""
    import cola_ia
    data = _load()
    pendientes = sorted(
        (it for it in data["items"].values()
         if not it.get("eval") and it.get("estado") != "descartada" and it.get("relevancia", 0) >= 40),
        key=lambda i: -i.get("relevancia", 0))[:n]
    for it in pendientes:
        cola_ia.encolar(f"oferta:{it['id']}", f"evaluar oferta «{it['titulo'][:40]}»",
                        lambda oid=it["id"]: (evaluar(oid), time.sleep(PAUSA)))
    if pendientes:
        cola_ia.encolar("ofertas:aviso", "avisar de las ofertas evaluadas",
                        lambda ids=[it["id"] for it in pendientes]: _avisar_evaluadas(ids))

def _avisar_evaluadas(ids: list):
    items = _load()["items"]
    evs   = [items[i]["eval"] for i in ids if i in items and items[i].get("eval")]
    if not evs:
        return
    rec    = [e.get("recomendacion", "") for e in evs]
    buenas = rec.count("postular")
    dudas  = rec.count("postular con reservas")
    msg = f"{len(evs)} ofertas evaluadas · {buenas} para postular · {dudas} con reservas"
    log(f"🧠 {msg}")
    _emit("ofertas_updated", {"evaluadas": len(evs)})
    try:
        from plyer import notification as _n
        _n.notify(title="💼 Ofertas listas", message=msg, timeout=10)
    except Exception:
        pass


# ─── Monitor automático (cada 5 h) ────────────────────────────────────────────
def _ofertas_loop():
    time.sleep(180)  # después de becas, para no coincidir con su arranque
    while True:
        try:
            _, nuevas = refresh()
            seg = sum(1 for it in _load()["items"].values() if _necesita_seguimiento(it))
            partes = []
            if nuevas:
                partes.append(f"{nuevas} ofertas nuevas que encajan")
            if seg:
                partes.append(f"{seg} candidaturas sin respuesta hace {DIAS_SEGUIMIENTO}+ días")
            if partes:
                try:
                    from plyer import notification as _n
                    _n.notify(title="💼 Ofertas de empleo", message=" · ".join(partes), timeout=10)
                except Exception:
                    pass
        except Exception as e:
            log(f"⚠ Monitor de ofertas: {e}")
        try:
            encolar_evaluaciones()
            import ingles
            ingles.encolar_extraccion()
        except Exception as e:
            log(f"⚠ Cola de evaluaciones: {e}")
        time.sleep(REFRESH_INTERVAL)

def start_ofertas_monitor():
    threading.Thread(target=_ofertas_loop, daemon=True).start()
