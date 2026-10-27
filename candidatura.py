"""
Centro de Control PRO — candidatura.py
Preparar una candidatura concreta: perfil del CV ajustado a la oferta, carta breve
y las preguntas de entrevista más probables con respuestas basadas en tu CV real.

Es lo que el repo original (ai-job-search) hacía con Claude + LaTeX y no se portó
con la pestaña Ofertas. Aquí va todo en local con Ollama.

Regla de oro: NADA inventado. El modelo solo recibe el CV maestro
(perfil.json → cv_maestro, sin las notas de estrategia) y los logros de Mi
Carrera, y después se comprueba: cada cifra que aparezca en el texto tiene que
estar en el CV, los logros o la oferta; si no, se marca como «revisa».
Se guarda en la propia oferta (campo «preparacion» de ofertas_data.json).
"""

import json
import os
import re
import subprocess
import time
import urllib.request

from extensions import socketio
from status import log
from rag import _ollama_post, _json_de, _json_ollama

import perfil

PERFIL  = perfil.get()
CV_FILE = os.path.expanduser(os.environ.get("CV_MAESTRO", PERFIL.get("cv_maestro", "~/MiPanelControl/cv/cv.md")))
MODELO  = "qwen3.5:4b"   # respaldo local si OmniRoute no está
# Modelo bueno vía OmniRoute (Kiro, gratis). Envía fuera el CV SIN datos de
# contacto (ver _cv) y la oferta: decisión del usuario.
OMNIROUTE_URL    = os.environ.get("OMNIROUTE_URL", "http://127.0.0.1:20128/v1/chat/completions")
OMNIROUTE_MODELO = os.environ.get("CANDIDATURA_MODELO", "kr/claude-sonnet-4.5")

# Dónde hizo cada cosa (perfil.json). Lo usan el prompt Y el revisor: con qwen 7b
# se mezclaban empresas («en la empresa A gestionaba lo de la empresa B»).
EMPRESAS       = PERFIL["empresas"]
EN_PREPARACION = PERFIL["en_preparacion"]
CERRADAS       = [e for e, d in EMPRESAS.items() if d.get("cerrada")]

def _mapa_empresas() -> str:
    return "\n".join(f"- {emp}: {', '.join(d['temas'][:12])}" for emp, d in EMPRESAS.items())

def _corto(empresa: str) -> str:
    return empresa.split(" (")[0]

REGLAS = """REGLAS OBLIGATORIAS:
- Cada ejemplo tiene que citar la empresa CORRECTA. Qué se hizo en cada sitio:
""" + _mapa_empresas() + f"""
- Certificaciones en preparación: SOLO {' y '.join(EN_PREPARACION) or 'ninguna'}. Nunca digas que preparas otra.
- Si la oferta pide algo que NO está en el CV (un producto, una certificación, una tecnología),
  dilo claro: «no lo he usado en producción», y relaciónalo con algo PARECIDO y REAL del CV.
""" + "".join(f"- Habla de {_corto(e)} SIEMPRE en pasado: esa etapa está cerrada.\n" for e in CERRADAS) + """- NO inventes anécdotas, incidencias, duraciones («en 40 minutos»), fechas ni planes futuros
  («me certificaré en…»). Cuenta solo lo que el CV dice. Si una pregunta pide un ejemplo
  concreto que el CV no trae, responde con lo que sí dice el CV y añade literalmente
  «[pon aquí un caso tuyo real]» para que el candidato lo complete con algo verdadero.
- Usa SOLO hechos del CV y de los logros. No inventes empresas, cifras, años, tecnologías ni certificaciones.
""" + "".join(f"- {r}\n" for r in PERFIL["reglas"]) + """- Español de España, tono profesional y directo, sin frases vacías."""

PROMPT_DOCS = """Eres un asesor de empleo IT en Madrid. Prepara la candidatura de este candidato
para la oferta. {reglas}

Responde SOLO en JSON:
{{"perfil": "párrafo de perfil profesional para el CV, 60-90 palabras, que use 3-4 términos exactos de la oferta",
"carta": "carta de presentación breve, 120-170 palabras, dirigida a la empresa, sin datos de contacto",
"palabras_clave": ["términos exactos de la oferta que conviene que aparezcan en el CV"],
"encaje": ["3 motivos concretos por los que encaja, cada uno apoyado en un hecho del CV"],
"huecos": ["lo que pide la oferta y el CV no cubre, dicho con honestidad"]}}

CV DEL CANDIDATO:
{cv}

LOGROS RECIENTES:
{logros}

OFERTA:
{oferta}
"""

PROMPT_ENTREVISTA = """Eres un entrevistador técnico de una empresa de Madrid que contrata para esta
oferta. Prepara al candidato. {reglas}

Responde SOLO en JSON:
{{"preguntas": [{{"pregunta": "pregunta probable en español", "por_que": "qué quiere comprobar el entrevistador",
"respuesta": "respuesta sugerida en primera persona, 50-90 palabras, apoyada SOLO en hechos del CV"}}],
"preguntas_en": [{{"pregunta": "pregunta sencilla en inglés", "respuesta": "respuesta corta en inglés sencillo (frases cortas, nivel A2-B1), 25-45 palabras", "traduccion": "traducción al español de la RESPUESTA (no de la pregunta)"}}]}}
Incluye 6 preguntas en español (técnicas y de experiencia, según la oferta) y 2 en inglés
(p. ej. «Tell me about yourself», «Describe your current role»).

CV DEL CANDIDATO:
{cv}

LOGROS RECIENTES:
{logros}

OFERTA:
{oferta}
"""


def _emit(evento: str, payload: dict):
    try:
        socketio.emit(evento, payload)
    except Exception:
        pass

def _cv() -> str:
    """CV maestro sin las notas de estrategia ni los datos de contacto."""
    with open(CV_FILE, encoding="utf-8") as f:
        texto = f.read()
    texto = texto.split("# 📋 NOTAS DE ESTRATEGIA")[0]
    texto = re.sub(r"^📍.*$|^🔗.*$|^.*credly\.com.*$", "", texto, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()

def _logros() -> str:
    try:
        import carrera
        return "\n".join(f"- {l.get('texto', '')}" for l in carrera._load().get("logros", [])[:20])
    except Exception:
        return ""

def _cifras_dudosas(texto: str, fuentes: str) -> list:
    """Números del texto generado que no aparecen en el CV, los logros ni la oferta."""
    fuentes_n = re.sub(r"[.\s]", "", fuentes)
    dudosas = []
    for n in set(re.findall(r"\d[\d.,]*", texto)):
        limpio = n.rstrip(".,").replace(".", "")
        if len(limpio) < 2 or limpio in fuentes_n:
            continue
        dudosas.append(n.rstrip(".,"))
    # «40 minutos», «3 horas»: el número puede estar en el CV (40+ usuarios) pero no la duración
    fuentes_l = fuentes.lower()
    for n, unidad in re.findall(r"(\d+)\s+(minutos?|horas?|d[ií]as?|semanas?|meses|minutes?|hours?|days?|weeks?)", texto, re.I):
        if f"{n} {unidad.lower()}" not in fuentes_l:
            dudosas.append(f"{n} {unidad}")
    return sorted(set(dudosas))

_NIEGA = re.compile(r"\bno (\w+ ){0,2}(tengo|he|dispongo|cumplo|poseo|cuento|conozco|est[aá]|figura|domino)\b|"
                    r"sin experiencia|aprendiendo|aprender|necesitar[ií]a|tendr[ií]a que|"
                    r"don't|do not|haven't|have not|not yet|todavía no|aún no", re.I)
_SIGLA = re.compile(r"\b[A-Z][A-Za-z0-9+/-]{2,}\b")

def _siglas(frase: str) -> list:
    """Siglas y nombres de producto: TODO MAYÚSCULAS, con mayúscula o cifra interna,
    o con mayúscula en mitad de la frase (la primera palabra no cuenta)."""
    salida = []
    for m in _SIGLA.finditer(frase):
        w = m.group(0)
        if w.isupper() or re.search(r"[a-z][A-Z0-9]|\d", w) or m.start() > 0:
            salida.append(w)
    return salida

def _frases(texto: str) -> list:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+|\n+", texto) if f.strip()]

def _revisar(prep: dict, cv: str, oferta: str, excluir: str = "", solo_precisas: bool = False) -> list:
    """Avisos sobre lo que el modelo pudo inventar. No corrige: señala para que lo mires."""
    cv_l, avisos = cv.lower(), []
    # el nombre de la empresa y del puesto salen en la carta con toda razón
    fuera = {w.lower() for w in re.findall(r"[\w/+-]+", excluir + " Estimado Estimada Responsable Nombre")}
    textos = [prep["perfil"], prep["carta"]] + prep["encaje"] + prep["huecos"] \
        + [q["respuesta"] for q in prep["preguntas"]] + [q["respuesta"] for q in prep["preguntas_en"]]
    vistos = set()
    def avisar(msg):
        if msg not in vistos:
            vistos.add(msg)
            avisos.append(msg)
    for frase in (f for t in textos for f in _frases(t)):
        fl = frase.lower()
        corta = frase if len(frase) < 110 else frase[:107] + "…"
        # 1. empresa equivocada: la frase nombra una empresa y un tema que es de OTRA
        nombradas = [e for e, d in EMPRESAS.items()
                     if any(re.search(rf"\b{re.escape(a)}\b", fl) for a in d["alias"])]
        if len(nombradas) == 1 and not solo_precisas:
            propia = EMPRESAS[nombradas[0]]["temas"]
            for e, d in EMPRESAS.items():
                if e == nombradas[0]:
                    continue
                ajenos = [t for t in d["temas"] if re.search(rf"\b{re.escape(t)}\b", fl) and t not in propia]
                if ajenos:
                    avisar(f"Empresa cambiada: «{corta}» — {', '.join(ajenos)} fue en {e.split(' (')[0]}, "
                           f"no en {nombradas[0].split(' (')[0]}")
        # 2. certificaciones «en preparación» que no lo están
        if re.search(r"preparaci[oó]n|preparando|estudiando para|preparing|studying for", fl):
            for sig in _siglas(frase):
                if sig.upper() not in EN_PREPARACION and sig.upper() not in ("AZ", "ASIR") \
                        and sig.lower() not in cv_l and sig.lower() in oferta.lower():
                    avisar(f"Dice que preparas «{sig}», y en tu plan solo están {', '.join(EN_PREPARACION)}: «{corta}»")
        # 3. una etapa cerrada contada en presente
        if re.search(r"\bactualmente\b|\bcurrently\b|\bnow\b|en la actualidad|\bI am an?\b|\bI'm an?\b", frase):
            for e in CERRADAS:
                d = EMPRESAS[e]
                if any(t in fl for t in d["alias"] + d["temas"][:6]):
                    avisar(f"Habla de {_corto(e)} en presente (esa etapa está cerrada): «{corta}»")
        # 4. se atribuye algo que solo sale en la oferta
        if not solo_precisas and not _NIEGA.search(frase):
            ajenas = sorted({s_ for s_ in _siglas(frase)
                             if s_.lower() not in cv_l and s_.lower() in oferta.lower()
                             and s_.lower() not in fuera
                             and s_.upper() not in EN_PREPARACION})
            if ajenas:
                avisar(f"Afirma «{', '.join(ajenas)}», que está en la oferta pero no en tu CV: «{corta}»")
    return avisos

PROMPT_AUDITOR = """Eres un revisor muy estricto. Compara el TEXTO GENERADO con el CV y los LOGROS
del candidato y localiza cada afirmación sobre el candidato que NO esté respaldada por ellos:
experiencia, herramientas, cifras, fechas, duraciones, anécdotas, detalles inventados (p. ej. «con
scripts Bash» si el CV dice otra herramienta), empresa equivocada, «trabajé» donde el CV dice
voluntariado, cursos dados por terminados que siguen en curso, planes o compromisos inventados.
Repasa CADA sección del texto, una por una, y sé exhaustivo: es mejor señalar de más.
Ejemplos de lo que SÍ hay que señalar: «completé el curso X» si el CV dice «en curso»; «trabajé en
Y» si el CV dice voluntariado; detalles técnicos añadidos que el CV no menciona (integraciones,
auditorías, herramientas concretas).
NO señales: frases donde reconoce que NO tiene algo, opiniones, motivación, lo que explica de la
oferta, ni que ya terminó una etapa que el CV da por cerrada ({cerradas}). Copia el fragmento EXACTO
(5-25 palabras) tal como aparece en el texto generado.
Responde SOLO en JSON: {{"dudas": [{{"fragmento": "texto exacto", "motivo": "qué dice el CV en realidad"}}]}}

CV:
{cv}

LOGROS:
{logros}

TEXTO GENERADO:
{texto}
"""

def _auditar(prep: dict, cv: str, logros: str) -> list:
    """Segunda pasada con el modelo bueno: frases no respaldadas por el CV."""
    secciones = [("Perfil", prep["perfil"]), ("Carta", prep["carta"])] \
        + [("Por qué encajas", e) for e in prep["encaje"]] \
        + [(q["pregunta"], q["respuesta"]) for q in prep["preguntas"] + prep["preguntas_en"]]
    texto = "\n\n".join(f"[{t}]\n{c}" for t, c in secciones)
    r = _chat_omniroute(PROMPT_AUDITOR.format(cv=cv, logros=logros, texto=texto,
                                             cerradas=", ".join(_corto(e) for e in CERRADAS) or "ninguna"))
    dudas = []
    for d in r.get("dudas", []) if isinstance(r.get("dudas"), list) else []:
        frag = str(d.get("fragmento", "")).strip().strip("«»\"")
        # solo lo que de verdad está en el texto (si no, el revisor se lo ha inventado)
        motivo = str(d.get("motivo", ""))
        # decir que una etapa cerrada terminó es correcto; el revisor a veces lo señala igualmente
        if CERRADAS and re.search(r"finish|termin|cerr|ended|closed", frag + " " + motivo, re.I) and \
                any(a in (frag + motivo).lower() for e in CERRADAS for a in EMPRESAS[e]["alias"] + [_corto(e).lower()]):
            continue
        if len(frag) > 8 and frag.lower() in texto.lower():
            dudas.append(f"«{frag[:140]}» — {motivo[:200]}")
    return dudas[:12]

def _omniroute_listo() -> bool:
    """Si OmniRoute está apagado (lo normal: no arranca con el equipo), lo enciende."""
    def responde():
        try:
            urllib.request.urlopen(OMNIROUTE_URL.rsplit("/v1/", 1)[0] + "/", timeout=3)
            return True
        except Exception:
            return False
    if responde():
        return True
    log("  🔌 OmniRoute estaba apagado: lo enciendo (unos segundos)…")
    subprocess.run(["podman", "start", "omniroute"], capture_output=True, timeout=60)
    for _ in range(30):
        time.sleep(1)
        if responde():
            return True
    return False

def _chat_omniroute(prompt: str) -> dict:
    clave = os.environ.get("OMNIROUTE_API_KEY", "")
    if not clave:
        raise RuntimeError("falta OMNIROUTE_API_KEY en .env")
    peticion = urllib.request.Request(OMNIROUTE_URL, method="POST", data=json.dumps({
        "model": OMNIROUTE_MODELO, "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {clave}"})
    with urllib.request.urlopen(peticion, timeout=240) as r:
        d = json.load(r)
    if d.get("error"):
        raise RuntimeError(str(d["error"].get("message", d["error"]))[:200])
    return _json_de(d["choices"][0]["message"]["content"])

def _chat_local(prompt: str) -> dict:
    r = _ollama_post("/api/chat", {
        "model": MODELO, "format": "json", "stream": False, "think": False,
        "options": {"temperature": 0.15, "num_ctx": 8192},
        "messages": [{"role": "user", "content": prompt}],
    }, timeout=600)
    return _json_ollama(r)

def _chat(prompt: str, usado: list) -> dict:
    """Primero el modelo bueno (OmniRoute); si falla, qwen local. `usado` recoge cuál respondió."""
    try:
        resultado = _chat_omniroute(prompt)
        usado.append(OMNIROUTE_MODELO)
        return resultado
    except Exception as e:
        log(f"  ⚠ OmniRoute no respondió ({str(e)[:120]}); uso el modelo local {MODELO}, que es más flojo")
    resultado = _chat_local(prompt)
    usado.append(MODELO)
    return resultado

def _txt(v, maximo=1500) -> str:
    return str(v or "").strip()[:maximo]

def _lista(v, maximo=8) -> list:
    return [str(x).strip()[:200] for x in v if str(x).strip()][:maximo] if isinstance(v, list) else []

def preparar(oid: str):
    """Corre en background (run_bg). Emite «ofertas_preparacion» al terminar."""
    import ofertas
    data = ofertas._load()
    it   = data["items"].get(oid)
    if not it:
        return
    log(f"📝 Preparando la candidatura para «{it['titulo'][:50]}»…")
    try:
        desc = it.get("descripcion") or (ofertas._descripcion(it) if it["fuente"] != "manual" else "")
    except Exception as e:
        desc = ""
        log(f"  ⚠ No pude leer la oferta completa ({e})")
    if not desc:
        msg = "⚠ Sin el texto de la oferta no puedo prepararla: usa «📋 Pegar texto de la oferta» y vuelve a probar"
        log(msg)
        _emit("ofertas_preparacion", {"id": oid, "error": msg})
        return
    try:
        cv = _cv()
    except Exception as e:
        msg = f"⚠ No encuentro el CV maestro ({CV_FILE}): {e}"
        log(msg)
        _emit("ofertas_preparacion", {"id": oid, "error": msg})
        return
    logros = _logros()
    oferta = (f"Puesto: {it['titulo']}\nEmpresa: {it.get('empresa') or '—'}\n"
              f"Ubicación: {it.get('ubicacion') or '—'} {it.get('modalidad') or ''}\n\n{desc[:5000]}")
    campos = dict(reglas=REGLAS, cv=cv, logros=logros, oferta=oferta)
    try:
        usado = []
        _omniroute_listo()
        docs = _chat(PROMPT_DOCS.format(**campos), usado)
        log("  📝 Perfil y carta listos; ahora las preguntas de entrevista…")
        ent = _chat(PROMPT_ENTREVISTA.format(**campos), usado)
    except Exception as e:
        msg = ("⚠ No pude hablar con Ollama. Enciende «Ollama (motor IA)» en la pestaña "
               f"Locales y vuelve a intentarlo. ({e})")
        log(msg)
        _emit("ofertas_preparacion", {"id": oid, "error": msg})
        return

    preguntas = [{"pregunta": _txt(p.get("pregunta"), 300), "por_que": _txt(p.get("por_que"), 300),
                  "respuesta": _txt(p.get("respuesta"), 1200)}
                 for p in ent.get("preguntas", []) if isinstance(p, dict) and p.get("pregunta")][:8]
    # qwen 7b a menudo «traduce» la pregunta en vez de la respuesta: eso no sirve, fuera
    preguntas_en = [{"pregunta": _txt(p.get("pregunta"), 300), "respuesta": _txt(p.get("respuesta"), 800),
                     "traduccion": "" if _txt(p.get("traduccion")).endswith("?")
                                   else _txt(p.get("traduccion"), 800)}
                    for p in ent.get("preguntas_en", []) if isinstance(p, dict) and p.get("pregunta")][:3]
    prep = {
        "perfil": _txt(docs.get("perfil")), "carta": _txt(docs.get("carta"), 2500),
        "palabras_clave": _lista(docs.get("palabras_clave"), 12),
        "encaje": _lista(docs.get("encaje"), 4), "huecos": _lista(docs.get("huecos"), 5),
        "preguntas": preguntas, "preguntas_en": preguntas_en,
        "modelo": " + ".join(dict.fromkeys(usado)), "fecha": ofertas._hoy(),
    }
    generado = " ".join([prep["perfil"], prep["carta"]] + prep["encaje"]
                        + [p["respuesta"] for p in preguntas])
    prep["revisar"] = _cifras_dudosas(generado, cv + logros + oferta)
    prep["avisos"] = []
    if OMNIROUTE_MODELO in usado:
        try:
            log("  📝 Revisando frase a frase contra tu CV…")
            # el revisor IA + las reglas que casi nunca dan falsos avisos
            prep["avisos"] = _auditar(prep, cv, logros) + _revisar(
                prep, cv + "\n" + logros, oferta, excluir=f"{it['titulo']} {it.get('empresa', '')}",
                solo_precisas=True)
            prep["revision"] = "IA"
        except Exception as e:
            log(f"  ⚠ La revisión con IA falló ({str(e)[:100]}); uso las reglas fijas")
    if "revision" not in prep:
        # respaldo (modelo local o revisor caído): reglas fijas, más ruidosas
        prep["avisos"] = _revisar(prep, cv + "\n" + logros, oferta,
                                  excluir=f"{it['titulo']} {it.get('empresa', '')}")
        prep["revision"] = "reglas"

    data = ofertas._load()
    if oid in data["items"]:
        data["items"][oid]["preparacion"] = prep
        data["items"][oid]["descripcion"] = data["items"][oid].get("descripcion") or desc[:8000]
        ofertas._save(data)
    n = len(prep["revisar"]) + len(prep["avisos"])
    aviso = f" — ⚠ {n} cosa{'s' if n > 1 else ''} que revisar antes de usarla" if n else ""
    log(f"📝 Candidatura preparada para «{it['titulo'][:50]}»{aviso}")
    _emit("ofertas_preparacion", {"id": oid})
