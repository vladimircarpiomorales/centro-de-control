"""
Centro de Control PRO — becas.py
Motor de búsqueda de cursos gratuitos, becas y vouchers de certificación.

Tres fuentes:
  1. Catálogo curado    — recursos siempre-gratis verificados (redes, seguridad, cloud, linux)
  2. Feeds RSS          — anuncios de nuevos cursos y convocatorias
  3. Búsqueda profunda  — rastreo web (DuckDuckGo) con consultas específicas

Los resultados se normalizan, deduplican por URL y persisten en becas_data.json.
Un hilo daemon refresca cada 5 h; la cola IA filtra lo nuevo y avisa de lo que sirve.
"""

import datetime
import hashlib
import html
import json
import os
import re
import ssl
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from extensions import socketio
from status import log
import almacen
import perfil

DATA_FILE        = os.path.expanduser(os.environ.get("BECAS_DATA", "~/MiPanelControl/becas_data.json"))
REFRESH_INTERVAL = 5 * 3600   # como Ofertas: varias veces al día
_lock            = threading.RLock()   # reentrante: _save lo vuelve a coger
_exclusivo = almacen.en_exclusiva(_lock)

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ─── Catálogo curado (siempre gratis, verificado) ──────────────────────────────
CATALOGO_CURADO = [
    {"title": "RIPE NCC Academy", "provider": "RIPE NCC",
     "url": "https://academy.ripe.net",
     "desc": "Cursos gratuitos de redes (BGP, IPv6, RPKI). Al completar el curso de IPv6 regalan un voucher para el examen de certificación IPv6 Fundamentals.",
     "tags": ["redes", "ipv6", "voucher"]},
    {"title": "Hurricane Electric IPv6 Certification", "provider": "Hurricane Electric",
     "url": "https://ipv6.he.net",
     "desc": "Certificación IPv6 100% gratuita y práctica, de nivel Newbie hasta Sage. Muy reconocida en el mundo del networking.",
     "tags": ["redes", "ipv6"]},
    {"title": "Cisco Networking Academy (Skills for All)", "provider": "Cisco",
     "url": "https://www.netacad.com",
     "desc": "Cursos gratuitos con insignia: Networking Basics, Networking Devices, Introducción a Ciberseguridad, Python, Linux. Camino directo de preparación CCNA.",
     "tags": ["redes", "seguridad", "linux"]},
    {"title": "Juniper Open Learning", "provider": "Juniper Networks",
     "url": "https://learningportal.juniper.net/juniper/user_activity_info.aspx?id=OPEN_LEARNING",
     "desc": "Cursos gratuitos de preparación JNCIA (Junos, seguridad, cloud, automatización) y al aprobar el examen de práctica dan voucher con 75% de descuento.",
     "tags": ["redes", "voucher"]},
    {"title": "Fortinet Training Institute — cursos gratis", "provider": "Fortinet",
     "url": "https://training.fortinet.com",
     "desc": "Toda la ruta de autoestudio NSE/FCF gratuita: Fortinet Certified Fundamentals y cursos técnicos de firewall, SD-WAN y ciberseguridad.",
     "tags": ["seguridad", "redes"]},
    {"title": "Palo Alto Networks — Digital Learning", "provider": "Palo Alto Networks",
     "url": "https://www.paloaltonetworks.com/services/education/digital-learning",
     "desc": "Cursos digitales gratuitos de ciberseguridad y fundamentos de sus tecnologías (firewall, SOC, cloud security).",
     "tags": ["seguridad"]},
    {"title": "ISC2 Certified in Cybersecurity (CC) — gratis", "provider": "ISC2",
     "url": "https://www.isc2.org/certifications/cc",
     "desc": "Programa 'One Million Certified in Cybersecurity': curso de autoestudio + examen de certificación CC totalmente gratis (requiere registrarse como candidato).",
     "tags": ["seguridad", "voucher"]},
    {"title": "EC-Council Essentials Series", "provider": "EC-Council",
     "url": "https://www.eccouncil.org/train-certify/essentials-series/",
     "desc": "Cursos Essentials de Ethical Hacking (EHE), Network Defense (NDE) y Digital Forensics (DFE) con contenido gratuito.",
     "tags": ["seguridad"]},
    {"title": "Microsoft Learn + Cloud Skills Challenge", "provider": "Microsoft",
     "url": "https://learn.microsoft.com/training/",
     "desc": "Rutas de aprendizaje gratuitas (Azure, seguridad, redes). Los Cloud Skills Challenge periódicos suelen regalar vouchers de examen de certificación.",
     "tags": ["cloud", "seguridad", "voucher"]},
    {"title": "AWS Skill Builder", "provider": "Amazon Web Services",
     "url": "https://skillbuilder.aws",
     "desc": "Más de 600 cursos gratuitos de cloud, redes y seguridad. AWS Educate ofrece además créditos y contenido para estudiantes.",
     "tags": ["cloud"]},
    {"title": "Google Cloud Skills Boost", "provider": "Google Cloud",
     "url": "https://www.cloudskillsboost.google",
     "desc": "Labs y cursos de Google Cloud; ofrecen créditos mensuales gratuitos y campañas con vouchers de certificación.",
     "tags": ["cloud", "voucher"]},
    {"title": "Grow with Google (Actívate)", "provider": "Google",
     "url": "https://grow.google/intl/es-419/",
     "desc": "Cursos y certificados gratuitos de tecnología y competencias digitales para Latinoamérica.",
     "tags": ["general", "beca"]},
    {"title": "IBM SkillsBuild", "provider": "IBM",
     "url": "https://skillsbuild.org",
     "desc": "Cursos gratuitos con credenciales digitales verificables: ciberseguridad, redes, cloud, IA y soporte TI.",
     "tags": ["cloud", "seguridad", "general"]},
    {"title": "Linux Foundation — cursos gratis y becas LiFT", "provider": "Linux Foundation",
     "url": "https://training.linuxfoundation.org/free-courses/",
     "desc": "Cursos introductorios gratuitos (Linux, Kubernetes, DevOps). Además, las becas LiFT anuales regalan formación y certificación completa.",
     "tags": ["linux", "beca"]},
    {"title": "OpenSecurityTraining2", "provider": "OST2",
     "url": "https://p.ost2.fyi",
     "desc": "Formación profunda y gratuita en seguridad de bajo nivel: arquitectura x86, ingeniería inversa, exploits, firmware.",
     "tags": ["seguridad"]},
    {"title": "TryHackMe — salas gratuitas", "provider": "TryHackMe",
     "url": "https://tryhackme.com",
     "desc": "Plataforma práctica de ciberseguridad con decenas de salas y rutas gratuitas (fundamentos, redes, pentesting).",
     "tags": ["seguridad"]},
    {"title": "Hack The Box Academy — módulos Tier 0", "provider": "Hack The Box",
     "url": "https://academy.hackthebox.com",
     "desc": "Los módulos Tier 0 (fundamentos de redes, Linux, web) son gratuitos usando los cubes que regalan al registrarse.",
     "tags": ["seguridad"]},
    {"title": "picoCTF", "provider": "Carnegie Mellon University",
     "url": "https://picoctf.org",
     "desc": "CTF educativo permanente y gratuito de CMU — la mejor puerta de entrada práctica a la seguridad ofensiva.",
     "tags": ["seguridad"]},
    {"title": "Qualys Free Training", "provider": "Qualys",
     "url": "https://www.qualys.com/training/",
     "desc": "Cursos y certificaciones gratuitas de gestión de vulnerabilidades, escaneo y cumplimiento.",
     "tags": ["seguridad", "voucher"]},
    {"title": "Oracle MyLearn — OCI gratis", "provider": "Oracle",
     "url": "https://mylearn.oracle.com",
     "desc": "Cursos gratuitos de Oracle Cloud Infrastructure. Varias veces al año abren promociones de certificación OCI con examen gratis.",
     "tags": ["cloud", "voucher"]},
    {"title": "Santander Open Academy (Becas Santander)", "provider": "Banco Santander",
     "url": "https://www.santanderopenacademy.com",
     "desc": "Becas y cursos gratuitos de tecnología, idiomas y habilidades. Convocatorias abiertas a Perú y toda Latinoamérica durante todo el año.",
     "tags": ["beca", "general"]},
    {"title": "Fundación Telefónica — Conecta Empleo", "provider": "Fundación Telefónica",
     "url": "https://conectaempleo-formacion.fundaciontelefonica.com",
     "desc": "Cursos gratuitos de competencias digitales y tecnología con certificado, orientados a empleabilidad en Latinoamérica.",
     "tags": ["general", "beca"]},
    {"title": "Capacítate para el Empleo", "provider": "Fundación Carlos Slim",
     "url": "https://capacitateparaelempleo.org",
     "desc": "Plataforma gratuita con cursos técnicos (redes, soporte, programación) y constancias descargables.",
     "tags": ["general", "redes"]},
    {"title": "PRONABEC — Becas del Estado Peruano", "provider": "PRONABEC (Perú)",
     "url": "https://www.pronabec.gob.pe",
     "desc": "Convocatorias de becas del Estado Peruano (Beca 18, Beca Generación del Bicentenario, becas de perfeccionamiento). Revisar fechas de cada convocatoria.",
     "tags": ["beca"]},
    {"title": "Coursera — Ayuda económica por curso", "provider": "Coursera",
     "url": "https://www.coursera.org",
     "desc": "Cada curso tiene el enlace 'Ayuda económica disponible': llenando la solicitud (aprueban en ~15 días) obtienes el curso y certificado gratis.",
     "tags": ["beca", "general"]},
    {"title": "edX — Auditar cursos gratis", "provider": "edX",
     "url": "https://www.edx.org",
     "desc": "Todos los cursos se pueden auditar gratis (sin certificado). También tienen programa de ayuda financiera con 90% de descuento.",
     "tags": ["beca", "general"]},
    {"title": "Cybrary — nivel gratuito", "provider": "Cybrary",
     "url": "https://www.cybrary.it",
     "desc": "Cursos gratuitos de ciberseguridad y preparación de certificaciones (Security+, CISSP, redes).",
     "tags": ["seguridad"]},
]

# ─── Feeds RSS de anuncios ─────────────────────────────────────────────────────
FEEDS_RSS = [
    {"name": "Class Central Report", "url": "https://www.classcentral.com/report/feed/"},
    {"name": "RIPE Labs",            "url": "https://labs.ripe.net/rss/"},
    {"name": "Linux Foundation Training", "url": "https://training.linuxfoundation.org/feed/"},
]

# ─── Fuentes Reddit (vía feeds RSS — la API JSON está bloqueada sin OAuth) ─────
# Listados: todo el contenido del subreddit es relevante
REDDIT_LISTADOS = [
    {"name": "r/udemyfreebies", "url": "https://www.reddit.com/r/udemyfreebies/new.rss"},
]

# Búsquedas dentro de subreddits técnicos (último mes, lo más nuevo)
REDDIT_BUSQUEDAS = [
    ("cybersecurity",     "free training OR free voucher OR free certification"),
    ("ccna",              "free voucher OR free course"),
    ("networking",        "free course OR free certification"),
    ("ITCareerQuestions", "free certification OR free training"),
]

# Pausa entre peticiones a Reddit — sin ella responde 429 (rate limit).
# Sin autenticación Reddit tolera ~1 petición cada 10 s por IP.
REDDIT_PAUSA = 15
REDDIT_REINTENTO = 60  # espera antes del único reintento tras un 429

# ─── Canales de Telegram (vista web pública t.me/s/ — sin cuenta ni bot) ───────
# filtrar=False en canales donde TODO el contenido es curso/cupón gratis
TELEGRAM_CANALES = [
    {"chan": "coursevania",         "name": "Coursevania",             "filtrar": False},
    {"chan": "discudemy",           "name": "DiscUdemy — Free Certs",  "filtrar": False},
    {"chan": "udemy_free_coupon",   "name": "Udemy Skill Up",          "filtrar": False},
    {"chan": "udemycoursecoupons",  "name": "Udemy 100% Free Coupons", "filtrar": False},
    {"chan": "becasyconvocatorias", "name": "Becas y Convocatorias",   "filtrar": True},
    {"chan": "opportunitiescorners","name": "Opportunities Corner",    "filtrar": True},
    # aportados por el usuario (auditados 2026-07-04):
    {"chan": "Udemy4U",             "name": "Udemy4U",                 "filtrar": False},  # enlaza directo a udemy.com
    {"chan": "udemyfreecourses13",  "name": "Udemy Free Courses",      "filtrar": False},  # usa trk.udemy.com (directo)
    {"chan": "CursosFacialix",      "name": "Facialix (español)",      "filtrar": False},  # blog es, resolver extrae link
    {"chan": "Udemy4",              "name": "Udemy4 (freecourse.io)",  "filtrar": False},  # resolver extrae link
]

# ─── Consultas de búsqueda profunda ────────────────────────────────────────────
BUSQUEDAS_PROFUNDAS = [
    "voucher gratis examen certificación redes ciberseguridad",
    "free certification exam voucher networking cybersecurity",
    "beca gratuita curso ciberseguridad redes latinoamérica",
    "free networking course certificate 2026",
    "becas cursos gratis tecnología Perú convocatoria",
]

# Palabras que debe contener un resultado dinámico para considerarse relevante
_KEYWORDS = ["gratis", "free", "beca", "scholarship", "voucher", "curso", "course",
             "certific", "training", "formación", "bootcamp", "grant"]


# Mensajes de servicio y spam habituales en los canales de cupones
_SPAM = re.compile(r"pinned a|netflix|join us|search bot|onlyfans|casino|apuestas|\bbet\b|crypto|"
                   r"airdrop|giveaway|premium account|spotify|hack(ed)? account", re.I)

DIAS_NUEVO         = 7    # pasado esto un hallazgo deja de contar como «nuevo»
DIAS_RETENER       = 45
DIAS_RETENER_TG    = 14   # los cupones de Telegram caducan en días


# ─── Utilidades HTTP / parsing ─────────────────────────────────────────────────
def _http_get(url: str, timeout: int = 12, ua: str = None) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": ua or _UA, "Accept-Language": "es,en"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="replace")

def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()

def _norm_url(u: str) -> str:
    p = urllib.parse.urlsplit(u.strip())
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query, ""))

def _make_id(url: str) -> str:
    return hashlib.sha1(_norm_url(url).encode()).hexdigest()[:12]

def _relevante(texto: str) -> bool:
    t = texto.lower()
    return any(k in t for k in _KEYWORDS)


# ─── Fetcher RSS/Atom ──────────────────────────────────────────────────────────
def _child_text(node, names) -> str:
    for c in node:
        tag = c.tag.split("}")[-1].lower()
        if tag in names:
            if tag == "link" and not (c.text and c.text.strip()):
                href = c.get("href")
                if href:
                    return href.strip()
            if c.text and c.text.strip():
                return c.text.strip()
    return ""

def _fetch_feed(feed: dict, max_items: int = 15) -> list:
    items = []
    try:
        root = ET.fromstring(_http_get(feed["url"]))
    except Exception:
        return items
    for node in root.iter():
        if node.tag.split("}")[-1].lower() not in ("item", "entry"):
            continue
        title = _strip_tags(_child_text(node, ("title",)))
        link  = _child_text(node, ("link",))
        desc  = _strip_tags(_child_text(node, ("description", "summary", "content")))[:280]
        fecha = _child_text(node, ("pubdate", "published", "updated"))[:16]
        if not title or not link.startswith("http"):
            continue
        if not _relevante(title + " " + desc):
            continue
        items.append({
            "title": title, "provider": feed["name"], "url": link,
            "desc": desc, "tags": ["anuncio"], "kind": "rss",
            "deadline": fecha or None,
        })
        if len(items) >= max_items:
            break
    return items


# ─── Fetcher Reddit (Atom RSS) ─────────────────────────────────────────────────
def _fetch_reddit(nombre: str, url: str, max_items: int = 12, filtrar: bool = True) -> list:
    import time
    items = []
    root  = None
    for intento in range(2):
        try:
            root = ET.fromstring(_http_get(url))
            break
        except Exception:
            if intento == 0:
                time.sleep(REDDIT_REINTENTO)
    if root is None:
        return items
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "entry":
            continue
        title = _strip_tags(_child_text(node, ("title",)))
        link  = _child_text(node, ("link",))
        fecha = _child_text(node, ("updated", "published"))[:10]
        if not title or not link.startswith("http"):
            continue
        if filtrar and not _relevante(title):
            continue
        items.append({
            "title": title[:140],
            "provider": nombre,
            "url": link,
            "desc": f"Publicación en {nombre}",
            "tags": ["reddit"], "kind": "reddit", "deadline": fecha or None,
        })
        if len(items) >= max_items:
            break
    return items

def _fetch_reddit_todo() -> list:
    import time
    encontrados = []
    for listado in REDDIT_LISTADOS:
        # en r/udemyfreebies todo es curso gratis: no filtrar por keywords
        lote = _fetch_reddit(listado["name"], listado["url"], filtrar=False)
        if lote:
            log(f"  👽 {listado['name']}: {len(lote)} publicaciones")
        encontrados.extend(lote)
        time.sleep(REDDIT_PAUSA)
    for sub, query in REDDIT_BUSQUEDAS:
        url = (f"https://www.reddit.com/r/{sub}/search.rss?"
               f"q={urllib.parse.quote(query)}&restrict_sr=on&sort=new&t=month")
        lote = _fetch_reddit(f"r/{sub}", url)
        if lote:
            log(f"  👽 r/{sub}: {len(lote)} resultados")
        encontrados.extend(lote)
        time.sleep(REDDIT_PAUSA)
    return encontrados


# ─── Fetcher Telegram (scraping de la vista web pública) ──────────────────────
def _fetch_telegram(canal: dict, max_items: int = 10) -> list:
    items = []
    try:
        page = _http_get(f"https://t.me/s/{canal['chan']}")
    except Exception:
        return items
    bloques = page.split('<div class="tgme_widget_message ')[1:]
    for b in reversed(bloques):  # la página lista viejo→nuevo; invertir para nuevos primero
        m_link  = re.search(r'class="tgme_widget_message_date" href="([^"]+)"', b)
        m_fecha = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})', b)
        m_texto = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', b, re.S)
        if not m_link or not m_texto:
            continue
        texto = _strip_tags(m_texto.group(1).replace("<br/>", " · "))
        if not texto:
            continue
        if canal.get("filtrar") and not _relevante(texto):
            continue
        if _SPAM.search(texto):
            continue
        items.append({
            "title": texto[:120],
            "provider": f"t.me/{canal['chan']}",
            "url": m_link.group(1),
            "desc": texto[120:380] if len(texto) > 120 else f"Canal «{canal['name']}» en Telegram",
            "tags": ["telegram"], "kind": "telegram",
            "deadline": m_fecha.group(1) if m_fecha else None,
        })
        if len(items) >= max_items:
            break
    return items

def _fetch_telegram_todo() -> list:
    import time
    encontrados = []
    for canal in TELEGRAM_CANALES:
        lote = _fetch_telegram(canal)
        if lote:
            log(f"  ✈ t.me/{canal['chan']}: {len(lote)} publicaciones")
        encontrados.extend(lote)
        time.sleep(2)
    return encontrados


# ─── Búsqueda profunda (DuckDuckGo HTML) ───────────────────────────────────────
def _buscar_ddg(query: str, max_results: int = 8) -> list:
    resultados = []
    try:
        page = _http_get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    except Exception:
        return resultados
    patron = r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    for m in re.finditer(patron, page, re.S):
        href, raw_title = m.group(1), m.group(2)
        title = _strip_tags(raw_title)
        if "uddg=" in href:  # DDG envuelve el destino en un redirect
            qs   = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = urllib.parse.unquote(qs.get("uddg", [href])[0])
        if not href.startswith("http") or not title:
            continue
        if not _relevante(title):
            continue
        dominio = urllib.parse.urlsplit(href).netloc.replace("www.", "")
        resultados.append({
            "title": title[:140], "provider": dominio, "url": href,
            "desc": f"Resultado de búsqueda: “{query}”", "tags": ["busqueda"],
            "kind": "busqueda", "deadline": None,
        })
        if len(resultados) >= max_results:
            break
    return resultados


# ─── Persistencia ──────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return {"items": [], "last_update": None}

def _save(data: dict):
    with _lock:
        almacen.guardar_json(DATA_FILE, data, indent=1)

def _norm_titulo(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()[:80]

def _depurar(items: list) -> list:
    """Quita spam, repetidos por título y lo caducado; «nuevo» solo dura DIAS_NUEVO días.
    Se aplica al guardar (refresh) y al mostrar, así los datos viejos también salen limpios."""
    hoy        = datetime.date.today()
    lim_nuevo  = (hoy - datetime.timedelta(days=DIAS_NUEVO)).isoformat()
    lim_tg     = (hoy - datetime.timedelta(days=DIAS_RETENER_TG)).isoformat()
    vistos, out = set(), []
    for it in sorted(items, key=_sort_key):
        if it.get("kind") == "telegram":
            if _SPAM.search(it.get("title", "")) or it.get("first_seen", "") < lim_tg:
                continue
        clave = _norm_titulo(it.get("title"))
        if clave in vistos:
            continue
        vistos.add(clave)
        if it.get("new") and it.get("first_seen", "") < lim_nuevo:
            it["new"] = False
        out.append(it)
    return out

def _sort_key(it):
    orden_kind = {"curado": 0, "telegram": 1, "reddit": 2, "rss": 3, "busqueda": 4}
    return (not it.get("new"), orden_kind.get(it.get("kind"), 3), it.get("title", "").lower())


# ─── API pública del motor ─────────────────────────────────────────────────────
@_exclusivo
def get_data() -> dict:
    data = _load()
    if not data["items"]:  # primera vez: sembrar catálogo curado al instante
        hoy = datetime.date.today().isoformat()
        for c in CATALOGO_CURADO:
            data["items"].append({**c, "id": _make_id(c["url"]), "kind": "curado",
                                  "deadline": c.get("deadline"), "first_seen": hoy, "new": False})
        _save(data)
    data["items"] = _depurar(data["items"])
    data["nuevos"] = sum(1 for i in data["items"] if i.get("new") and _veredicto(i) != "basura")
    return data

def refresh(deep: bool = False) -> tuple:
    """Reconstruye el índice: catálogo + RSS (+ búsqueda profunda). Devuelve (total, nuevos)."""
    modo = "profunda" if deep else "estándar"
    log(f"🎓 Buscando becas y cursos gratis (búsqueda {modo})...")

    hoy         = datetime.date.today().isoformat()
    candidatos  = []

    for c in CATALOGO_CURADO:
        candidatos.append({**c, "kind": "curado", "deadline": c.get("deadline")})

    n_rss = 0
    for feed in FEEDS_RSS:
        encontrados = _fetch_feed(feed)
        if encontrados:
            log(f"  📡 {feed['name']}: {len(encontrados)} anuncios relevantes")
        n_rss += len(encontrados)
        candidatos.extend(encontrados)

    telegram = _fetch_telegram_todo()
    reddit   = _fetch_reddit_todo()
    candidatos.extend(telegram)
    candidatos.extend(reddit)
    # salud de los lectores, por familias (un canal suelto puede estar tranquilo un día)
    import salud_fuentes
    salud_fuentes.registrar("becas:rss", "Feeds RSS (becas)", n_rss)
    salud_fuentes.registrar("becas:telegram", "Telegram (becas)", len(telegram))
    salud_fuentes.registrar("becas:reddit", "Reddit (becas)", len(reddit))

    if deep:
        for query in BUSQUEDAS_PROFUNDAS:
            encontrados = _buscar_ddg(query)
            if encontrados:
                log(f"  🔎 “{query[:40]}…”: {len(encontrados)} resultados")
            candidatos.extend(encontrados)

    with _lock:   # releer, aplicar y guardar sin que otra petición se cuele en medio
        prev        = {i["id"]: i for i in _load()["items"]}   # leído tras buscar: no se pierde un «visto» marcado mientras tanto
        primera_vez = not prev
        items, nuevos = {}, 0
        for c in candidatos:
            cid = _make_id(c["url"])
            if cid in items:
                continue
            anterior = prev.get(cid)
            if anterior:
                c["first_seen"] = anterior.get("first_seen", hoy)
                c["new"]        = anterior.get("new", False)
                if anterior.get("ia"):
                    c["ia"] = anterior["ia"]
            else:
                c["first_seen"] = hoy
                c["new"]        = not primera_vez  # el primer llenado es línea base, no novedad
                if c["new"]:
                    nuevos += 1
            items[cid] = {**c, "id": cid}

        # conservar hallazgos dinámicos previos que esta pasada no volvió a ver (rotación
        # de feeds), pero solo por 45 días — los cupones y convocatorias caducan
        limite = (datetime.date.today() - datetime.timedelta(days=DIAS_RETENER)).isoformat()
        for cid, viejo in prev.items():
            if cid not in items and viejo.get("kind") in ("rss", "busqueda", "reddit", "telegram"):
                if viejo.get("first_seen", "") >= limite:
                    items[cid] = viejo

        depurados = _depurar(list(items.values()))
        nuevos    = sum(1 for i in depurados if i.get("new") and i.get("first_seen") == hoy)
        items     = {i["id"]: i for i in depurados}
        data = {"items": depurados,
                "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        _save(data)

    log(f"✅ Becas/cursos: {len(items)} recursos en el índice ({nuevos} nuevos)")
    try:
        socketio.emit("becas_updated", {"total": len(items), "nuevos": nuevos})
    except Exception:
        pass
    return len(items), nuevos

@_exclusivo
def marcar_vistos():
    data = _load()
    for i in data["items"]:
        i["new"] = False
    _save(data)


# ─── Resolvedor de enlace directo ──────────────────────────────────────────────
# Muchos canales de cupones enlazan a blogs intermedios llenos de publicidad y
# redirecciones. Este resolvedor extrae el enlace final de Udemy (con cupón) del
# HTML intermedio, sin pasar por los muros de anuncios.
_RE_UDEMY_CURSO = re.compile(r'https?://(?:www\.)?udemy\.com/course/[^"\'<>\s\\]+')
_RE_UDEMY_TRK   = re.compile(r'https?://trk\.udemy\.com/[^"\'<>\s\\]+')

def _extraer_udemy(texto: str) -> list:
    """Enlaces directos a cursos de Udemy hallados en un HTML — con cupón primero."""
    encontrados = []
    for m in _RE_UDEMY_TRK.findall(texto):
        # trk.udemy.com lleva el destino urlencodeado en el parámetro u=
        qs      = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(m)).query)
        destino = qs.get("u", [None])[0]
        if destino:
            encontrados.append(urllib.parse.unquote(destino))
    encontrados += [html.unescape(x) for x in _RE_UDEMY_CURSO.findall(texto)]
    con_cupon = [x for x in encontrados if "couponcode" in x.lower()]
    return con_cupon + [x for x in encontrados if x not in con_cupon]

def resolver_directo(url: str):
    """Intenta obtener el enlace directo de Udemy detrás de una publicación.
    Devuelve la URL directa o None si no se encuentra."""
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
        if host.endswith("udemy.com") and not host.startswith("trk."):
            return url
        directos = _extraer_udemy(url)  # la propia URL puede ser trk.udemy.com
        if directos:
            return directos[0]

        candidatas = []
        if host in ("t.me", "telegram.me"):
            sep  = "&" if "?" in url else "?"
            page = _http_get(url + sep + "embed=1")
            directos = _extraer_udemy(page)
            if directos:
                return directos[0]
            for h in re.findall(r'href="(https?://[^"]+)"', page):
                h  = html.unescape(h)
                hh = urllib.parse.urlsplit(h).netloc.lower()
                if hh.endswith(("t.me", "telegram.org", "telegram.me")) or "google" in hh:
                    continue
                if h not in candidatas:
                    candidatas.append(h)
            candidatas = candidatas[:3]
        else:
            candidatas = [url]

        for c in candidatas:
            try:
                cuerpo = _http_get(c)
            except Exception:
                continue
            directos = _extraer_udemy(cuerpo)
            if directos:
                return directos[0]
    except Exception:
        pass
    return None


# ─── Filtro con IA local (cola_ia) ─────────────────────────────────────────────
# Telegram y Reddit traen mucho ruido: cupones de cosas que no son IT, descuentos de
# pago, sorteos… El modelo local separa lo que le sirve al usuario (perfil.json → perfil_becas) de lo que no.
MODELO_FILTRO = "qwen3.5:4b"
POR_LLAMADA   = 10    # elementos por petición al modelo
POR_TANDA     = 200   # tope por búsqueda (~13 min); lo que sobre se hace en la siguiente
VEREDICTOS    = ("sirve", "dudosa", "basura")

PROMPT_FILTRO = (
    "Clasifica estos anuncios de cursos, becas y vouchers para una persona concreta: "
    + perfil.get().get("perfil_becas", "técnico de redes y sistemas; busca formación gratuita.") + "\n\n"
    "Para cada anuncio elige:\n"
    "- «sirve»: gratis (o voucher/beca/cupón al 100 %) y de su área: redes, Linux, sistemas, "
    "cloud, seguridad, scripting/automatización, certificaciones IT, inglés técnico, o becas "
    "a las que puede optar.\n"
    "- «dudosa»: puede servir pero no está claro (no dice si es gratis, área cercana pero no "
    "la suya, programación general, ofimática avanzada).\n"
    "- «basura»: de pago o solo descuento, nada que ver con IT (marketing, cocina, finanzas "
    "personales, yoga…), spam, sorteos, noticias sin curso.\n"
    "motivo: 3-10 palabras en castellano con el porqué.\n\n"
    "Responde SOLO con JSON: {\"r\": [{\"n\": <número>, \"v\": \"sirve|dudosa|basura\", "
    "\"motivo\": \"…\"}]} con una entrada por anuncio.\n\nANUNCIOS:\n"
)

def _veredicto(it: dict) -> str:
    return (it.get("ia") or {}).get("v", "")

def _sin_clasificar() -> list:
    """Los dinámicos sin veredicto, los más recientes primero (el catálogo curado ya es bueno)."""
    items = [i for i in _depurar(_load()["items"])
             if i.get("kind") != "curado" and not i.get("ia")]
    return sorted(items, key=lambda i: i.get("first_seen", ""), reverse=True)

def clasificar(ids: list, modelo: str = MODELO_FILTRO) -> int:
    """Clasifica un grupo de anuncios con una sola llamada. Devuelve cuántos quedaron."""
    from rag import _ollama_post, _json_ollama
    por_id = {i["id"]: i for i in _load()["items"]}
    grupo  = [por_id[i] for i in ids if i in por_id and not por_id[i].get("ia")]
    if not grupo:
        return 0
    texto = "\n".join(
        f"{n}. {it.get('title', '')[:160]} — {it.get('provider', '')} — "
        f"{re.sub(r'\s+', ' ', it.get('desc') or '')[:220]}"
        for n, it in enumerate(grupo, 1))
    r = _ollama_post("/api/chat", {
        "model": modelo, "format": "json", "stream": False, "think": False,
        "options": {"temperature": 0.1},
        "messages": [{"role": "user", "content": PROMPT_FILTRO + texto}],
    }, timeout=300)
    hoy, res = datetime.date.today().isoformat(), {}
    for e in _json_ollama(r).get("r", []):
        try:
            n = int(e.get("n"))
        except (TypeError, ValueError):
            continue
        v = str(e.get("v", "")).strip().lower()
        if 1 <= n <= len(grupo) and v in VEREDICTOS:
            res[grupo[n - 1]["id"]] = {"v": v, "motivo": str(e.get("motivo", ""))[:90], "fecha": hoy}
    with _lock:   # releer: mientras pensaba pudo llegar otra búsqueda o un «marcar vistos»
        data = _load()
        for it in data["items"]:
            if it["id"] in res:
                it["ia"] = res[it["id"]]
        _save(data)
    return len(res)

def encolar_clasificaciones(n: int = POR_TANDA):
    import cola_ia
    pendientes = [i["id"] for i in _sin_clasificar()[:n]]
    for k in range(0, len(pendientes), POR_LLAMADA):
        ids = pendientes[k:k + POR_LLAMADA]
        cola_ia.encolar(f"becas:{ids[0]}", f"clasificar {len(ids)} becas/cursos",
                        lambda ids=ids: clasificar(ids))
    if pendientes:
        cola_ia.encolar("becas:aviso", "avisar de las becas que sirven",
                        lambda ids=set(pendientes): _avisar_clasificadas(ids))

def _avisar_clasificadas(ids: set):
    items = [i for i in _load()["items"] if i["id"] in ids and i.get("ia")]
    sirven = [i for i in items if _veredicto(i) == "sirve"]
    basura = sum(1 for i in items if _veredicto(i) == "basura")
    log(f"🎓 Filtro IA: {len(items)} revisados · {len(sirven)} te sirven · {basura} descartados")
    try:
        socketio.emit("becas_updated", {"clasificados": len(items)})
    except Exception:
        pass
    nuevos = [i for i in sirven if i.get("new")]
    if nuevos:
        try:
            from plyer import notification as _n
            _n.notify(title=f"🎓 {len(nuevos)} cursos/becas que te sirven",
                      message=nuevos[0].get("title", "")[:120], timeout=10)
        except Exception:
            pass


# ─── Monitor automático (cada 5 h) ────────────────────────────────────────────
def _becas_loop():
    import time
    time.sleep(90)  # dejar que el panel termine de arrancar
    while True:
        try:
            refresh(deep=False)
        except Exception:
            pass
        try:
            # el aviso de escritorio lo da la cola IA al terminar, contando solo lo que sirve
            encolar_clasificaciones()
        except Exception as e:
            log(f"⚠ Cola de clasificación de becas: {e}")
        time.sleep(REFRESH_INTERVAL)

def start_becas_monitor():
    threading.Thread(target=_becas_loop, daemon=True).start()
