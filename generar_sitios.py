"""
Centro de Control PRO — generar_sitios.py
Genera extension-metube/sitios.json con los dominios que yt-dlp sabe extraer.

Para qué: que la extensión pueda decir "de aquí se puede descargar" mientras
navegas, al instante y sin mandar tu URL a ningún sitio. La sonda del panel sigue
siendo la respuesta autorizada (sabe de login, DRM y geobloqueo); esta lista es
solo la pista rápida.

Cómo: los `_VALID_URL` de los extractores traen los dominios literales, con los
puntos escapados ("udemy\\.com"). Se extraen de ahí. Es heurístico — un extractor
que construya su patrón de forma rara se perderá — pero cubre la gran mayoría.

Uso:  ~/MiPanelControl/metube/venv/bin/python generar_sitios.py
"""

import json
import os
import re

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "extension-metube", "sitios.json")

# Secuencias tipo "algo\.algo(\.algo)*" dentro del regex del extractor.
DOMINIO_RE = re.compile(r"([a-z0-9][a-z0-9-]{0,62}(?:\\?\.[a-z0-9][a-z0-9-]{0,62})+)")

TLDS_VALIDAS = {
    "com", "net", "org", "tv", "co", "io", "me", "fm", "es", "pe", "mx", "ar",
    "cl", "br", "de", "fr", "it", "nl", "pl", "ru", "jp", "kr", "cn", "uk",
    "us", "ca", "au", "in", "edu", "gov", "info", "biz", "online", "live",
    "app", "dev", "xyz", "to", "cc", "ly", "sh", "at", "be", "ch", "cz", "dk",
    "fi", "gr", "hu", "ie", "il", "no", "nz", "pt", "ro", "se", "sk", "tr",
    "tw", "ua", "vn", "za", "media", "news", "video", "watch", "digital",
    "eu", "asia", "cat", "is", "lt", "lv", "ee", "si", "hr", "rs", "bg",
    "kz", "th", "id", "my", "ph", "sg", "hk", "ae", "sa", "eg", "ng", "ke",
    "ma", "pk", "bd", "lk", "np", "by", "ba", "mk", "al", "ge", "am", "az",
}

# Ruido conocido: fragmentos de regex que parecen dominio pero no lo son.
BASURA = {
    "www", "http", "https", "mp4", "m3u8", "js", "json", "html", "php", "aspx",
    "index", "com.com", "s.s", "a.b", "x.y",
}


# Los dominios no siempre son literales. Tres formas frecuentes que hay que
# expandir o se pierde el sitio entero:
#   (?:com|eu)          TLD en alternancia   -> panopto.com, panopto.eu
#   reddit(?:media)?    grupo opcional       -> reddit.com, redditmedia.com
#   \.[a-z]{2,3}        TLD como clase       -> dailymotion.com, .net, ...
OPCIONAL_RE   = re.compile(r"\((?:\?:)?([a-z0-9-]+)\)\?")
ALTERNATIVA_RE = re.compile(r"\((?:\?:)?([a-z0-9-]+(?:\|[a-z0-9-]+)+)\)")
CLASE_TLD_RE  = re.compile(r"\[a-z\]\{\d(?:\s*,\s*\d+)?\}")
TLDS_COMUNES  = ["com", "net", "org", "tv", "es", "de", "fr", "it", "co"]
MAX_VARIANTES = 40


def variantes(patron):
    """Expande grupos opcionales, alternancias y clases de TLD en cadenas planas."""
    salida = [patron]

    for regex, opciones in (
        (OPCIONAL_RE,    lambda m: ["", m.group(1)]),
        (ALTERNATIVA_RE, lambda m: m.group(1).split("|")),
        (CLASE_TLD_RE,   lambda m: TLDS_COMUNES),
    ):
        # Varias pasadas: un patrón puede traer más de un grupo del mismo tipo.
        for _ in range(3):
            nuevas, cambio = [], False
            for p in salida:
                m = regex.search(p)
                if not m:
                    nuevas.append(p)
                    continue
                cambio = True
                for op in opciones(m):
                    nuevas.append(p[:m.start()] + op + p[m.end():])
            salida = nuevas[:MAX_VARIANTES]
            if not cambio:
                break

    return salida


def extraer():
    from yt_dlp.extractor import gen_extractor_classes

    dominios = set()
    sin_patron = 0

    for ie in gen_extractor_classes():
        patron = getattr(ie, "_VALID_URL", None)
        if not isinstance(patron, str) or not patron:
            sin_patron += 1
            continue

        brutos = []
        for v in variantes(patron.lower()):
            brutos += DOMINIO_RE.findall(v)

        for bruto in brutos:
            d = bruto.replace("\\", "")
            if d in BASURA or d.count(".") > 3:
                continue
            partes = d.split(".")
            if len(partes) < 2 or partes[-1] not in TLDS_VALIDAS:
                continue
            # Quitar el "www." delantero: el matcher ya compara por sufijo.
            if partes[0] == "www":
                partes = partes[1:]
            if len(partes) < 2 or len(partes[0]) < 2:
                continue
            dominios.add(".".join(partes))

    return sorted(dominios), sin_patron


def _version_ytdlp():
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return "?"


if __name__ == "__main__":
    import sys

    dominios, sin_patron = extraer()

    # --stdout: emite JSON para que el panel lo capture como subproceso. Hace
    # falta porque el venv del panel NO tiene yt-dlp — solo el de MeTube, que es
    # además el que hace las descargas, así que la lista sale de la versión
    # correcta por construcción.
    if "--stdout" in sys.argv:
        json.dump(
            {"version": _version_ytdlp(), "n": len(dominios), "dominios": dominios},
            sys.stdout, ensure_ascii=False, separators=(",", ":"),
        )
        sys.exit(0)

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(dominios, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(SALIDA) / 1024
    print(f"{len(dominios)} dominios -> {SALIDA} ({kb:.0f} KB)")
    print(f"({sin_patron} extractores sin _VALID_URL usable)")
    print(f"yt-dlp {_version_ytdlp()}")
