"""
Organizador IA — Clasifica y mueve archivos usando Ollama (IA local) + reglas por extensión.
"""

import os
import shutil
import json
import mimetypes
import subprocess
from pathlib import Path

# ─── Categorías predefinidas ──────────────────────────────────────────────────
CATEGORIAS = {
    "Documentos": {
        "emoji": "📄",
        "exts": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".txt", ".md", ".odt", ".csv", ".epub", ".rtf"},
        "mime": {"application/pdf", "text/plain", "text/markdown", "application/msword",
                 "application/vnd.openxmlformats-officedocument"},
    },
    "Imagenes": {
        "emoji": "🖼️",
        "exts": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff", ".heic"},
        "mime": {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/svg+xml"},
    },
    "Audios": {
        "emoji": "🎵",
        "exts": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"},
        "mime": {"audio/mpeg", "audio/wav", "audio/flac", "audio/ogg", "audio/mp4"},
    },
    "Videos": {
        "emoji": "🎬",
        "exts": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "mime": {"video/mp4", "video/x-matroska", "video/avi", "video/quicktime", "video/webm"},
    },
    "Archivos": {
        "emoji": "📦",
        "exts": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".dmg"},
        "mime": {"application/zip", "application/x-rar-compressed",
                 "application/gzip", "application/x-7z-compressed", "application/x-iso9660-image"},
    },
    "Programas": {
        "emoji": "💻",
        "exts": {".exe", ".AppImage", ".deb", ".rpm", ".sh", ".bin", ".run", ".dmg", ".flatpakref"},
        "mime": {"application/x-executable", "application/x-sharedlib", "application/x-msdownload"},
    },
    "Codigo": {
        "emoji": "⚙️",
        "exts": {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
                 ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash",
                 ".html", ".css", ".scss", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
                 ".conf", ".sql", ".dockerfile", ".env", ".gitignore"},
        "mime": {"text/x-python", "text/javascript", "text/html", "text/css", "application/json"},
    },
    "Otros": {
        "emoji": "📁",
        "exts": set(),
        "mime": set(),
    },
}

# ─── Clasificador ─────────────────────────────────────────────────────────────
CLASIFICAR_PROMPT = """Eres un clasificador de archivos. Responde SOLO con el nombre de la categoría, nada más.

Categorías disponibles: Documentos, Imagenes, Audios, Videos, Archivos, Programas, Codigo, Otros

Reglas:
- Documentos: PDFs, Word, Excel, presentaciones, texto plano, libros
- Imagenes: fotos, dibujos, capturas de pantalla, gráficos
- Audios: música, podcasts, grabaciones
- Videos: películas, clips, tutoriales grabados
- Archivos: comprimidos, ISOs, discos
- Programas: ejecutables, instaladores, scripts binarios
- Codigo: código fuente, configuraciones técnicas
- Otros: cualquier cosa que no encaje arriba

Archivo: "{filename}"
Tamaño: {size} bytes
Tipo: {mime}
Categoría:"""


def _clasificar_por_extension(ext: str) -> str:
    for cat, info in CATEGORIAS.items():
        if ext.lower() in info["exts"]:
            return cat
    return "Otros"


def _clasificar_por_mime(mime: str) -> str | None:
    for cat, info in CATEGORIAS.items():
        if mime in info["mime"]:
            return cat
    return None


def _clasificar_con_ollama(filename: str, size: int, mime: str) -> str | None:
    prompt = CLASIFICAR_PROMPT.format(filename=filename, size=size, mime=mime)
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:11434/api/generate",
             "-d", json.dumps({"model": "llama3.2:3b", "prompt": prompt,
                              "stream": False, "options": {"num_predict": 20}})],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout)
        respuesta = data.get("response", "").strip().strip('"').strip("'")
        # Validar que sea una categoría válida
        for cat in CATEGORIAS:
            if cat.lower() in respuesta.lower():
                return cat
    except Exception:
        pass
    return None


def clasificar_archivo(ruta: str, usar_ia: bool = True) -> str:
    """Determina la categoría de un archivo. Retorna nombre de categoría."""
    p = Path(ruta)
    ext = p.suffix.lower()
    size = p.stat().st_size if p.exists() else 0
    mime, _ = mimetypes.guess_type(ruta)
    mime = mime or ""

    # 1. Por MIME
    cat = _clasificar_por_mime(mime)
    if cat:
        return cat

    # 2. Por extensión
    cat = _clasificar_por_extension(ext)
    if cat != "Otros":
        return cat

    # 3. IA local (si está disponible y se solicita)
    if usar_ia:
        cat = _clasificar_con_ollama(p.name, size, mime)
        if cat:
            return cat

    return "Otros"


# ─── Organizador ──────────────────────────────────────────────────────────────
def escanear(origenes: list[str], usar_ia: bool = True, max_archivos: int = 0) -> list[dict]:
    """Escanea directorios y clasifica archivos. Retorna lista de {ruta, categoria, destino}."""
    resultados = []
    contador = 0

    for origen in origenes:
        dir_path = os.path.expanduser(origen)
        if not os.path.isdir(dir_path):
            continue
        for entry in os.scandir(dir_path):
            if not entry.is_file():
                continue
            if entry.name.startswith("."):
                continue
            cat = clasificar_archivo(entry.path, usar_ia=usar_ia)
            destino = os.path.expanduser(f"~/Organizado/{cat}")
            resultados.append({
                "ruta": entry.path,
                "nombre": entry.name,
                "categoria": cat,
                "destino": destino,
                "tamano": entry.stat().st_size,
            })
            contador += 1
            if max_archivos and contador >= max_archivos:
                break
        if max_archivos and contador >= max_archivos:
            break

    return resultados


def organizar(resultados: list[dict], dry_run: bool = True) -> dict:
    """Mueve archivos a sus carpetas de categoría. Retorna resumen."""
    resumen = {"movidos": 0, "errores": 0, "saltados": 0, "detalle": []}

    for item in resultados:
        origen = item["ruta"]
        destino_dir = item["destino"]
        nombre = item["nombre"]

        if not os.path.exists(origen):
            resumen["saltados"] += 1
            continue

        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, nombre)

        # Evitar colisiones
        if os.path.exists(destino):
            base, ext = os.path.splitext(nombre)
            contador = 1
            while os.path.exists(os.path.join(destino_dir, f"{base}_{contador}{ext}")):
                contador += 1
            destino = os.path.join(destino_dir, f"{base}_{contador}{ext}")

        if dry_run:
            resumen["detalle"].append(f"  → {nombre} → {item['categoria']}/")
            resumen["movidos"] += 1
        else:
            try:
                shutil.move(origen, destino)
                resumen["detalle"].append(f"  ✓ {nombre} → {item['categoria']}/")
                resumen["movidos"] += 1
            except Exception as e:
                resumen["detalle"].append(f"  ✗ {nombre}: {e}")
                resumen["errores"] += 1

    return resumen


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Organizador IA de archivos")
    parser.add_argument("origenes", nargs="*", default=["~/Descargas", "~/Desktop"],
                        help="Directorios a organizar")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Solo mostrar qué se movería (por defecto)")
    parser.add_argument("--run", action="store_true",
                        help="Ejecutar realmente los movimientos")
    parser.add_argument("--no-ia", action="store_true",
                        help="No usar Ollama, solo reglas por extensión")
    parser.add_argument("--max", type=int, default=0,
                        help="Máximo de archivos a procesar (0 = todos)")
    args = parser.parse_args()

    usar_ia = not args.no_ia
    resultados = escanear(args.origenes, usar_ia=usar_ia, max_archivos=args.max)
    ejecutar = args.run and not args.dry_run

    if not resultados:
        print("📭 No se encontraron archivos para organizar.")
        exit(0)

    print(f"\n📊 Archivos encontrados: {len(resultados)}\n")

    # Agrupar por categoría
    por_cat = {}
    for r in resultados:
        por_cat.setdefault(r["categoria"], []).append(r)

    for cat, items in sorted(por_cat.items()):
        emoji = CATEGORIAS.get(cat, {}).get("emoji", "📁")
        print(f"  {emoji} {cat}: {len(items)} archivos")

    print()
    resumen = organizar(resultados, dry_run=not ejecutar)

    print(f"\n{'─' * 50}")
    if ejecutar:
        print(f"✅ {resumen['movidos']} archivos organizados")
    else:
        print(f"🔍 Vista previa: {resumen['movidos']} archivos se moverían")
    if resumen["errores"]:
        print(f"❌ {resumen['errores']} errores")
    if resumen["saltados"]:
        print(f"⏭️  {resumen['saltados']} saltados")
