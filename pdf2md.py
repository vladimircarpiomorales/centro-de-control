"""
Conversor PDF → Markdown usando Docling.
"""

import glob
import os
import threading
import time

from services import RUTA_MANUALES_MD


def _contar_paginas(pdf_path):
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf_path)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return None


def _convertir_uno(converter, pdf_path: str, output_dir: str, log, on_progress=None, seg_por_pagina=0.45):
    from pathlib import Path
    from docling_core.types.doc.base import ImageRefMode

    nombre = os.path.splitext(os.path.basename(pdf_path))[0]
    md_path = Path(output_dir) / f"{nombre}.md"
    artifacts_name = f"{nombre}_img"
    artifacts_dir = Path(output_dir) / artifacts_name

    total_paginas = _contar_paginas(pdf_path)
    stop_event = threading.Event()
    ticker = None
    if on_progress and total_paginas:
        def _tick():
            inicio = time.time()
            estimado = max(total_paginas * seg_por_pagina, 3)
            while not stop_event.wait(1):
                pct = min(95, int((time.time() - inicio) / estimado * 100))
                on_progress(nombre, pct)
        ticker = threading.Thread(target=_tick, daemon=True)
        ticker.start()

    log(f"📄 Convirtiendo {os.path.basename(pdf_path)}...")
    try:
        result = converter.convert(pdf_path)
        # artifacts_dir relativo (solo el nombre) para que el .md quede con rutas relativas
        result.document.save_as_markdown(md_path, artifacts_dir=Path(artifacts_name), image_mode=ImageRefMode.REFERENCED)
    finally:
        stop_event.set()
        if ticker:
            ticker.join(timeout=2)
        if on_progress:
            on_progress(nombre, 100)

    paginas = result.document.num_pages()
    tamano = os.path.getsize(md_path)
    n_imgs = len(os.listdir(artifacts_dir)) if os.path.isdir(artifacts_dir) else 0
    log(f"✅ {nombre}.md listo — {paginas} páginas, {n_imgs} imágenes, {tamano // 1024} KB")
    return md_path


def convertir(pdf_path: str, output_dir: str = RUTA_MANUALES_MD, callback_log=None, on_progress=None):
    """Convierte un PDF (o todos los PDF de una carpeta) a Markdown con Docling.

    on_progress(nombre, percent) recibe un % ESTIMADO (por tiempo transcurrido vs.
    páginas totales), no un progreso exacto — Docling no expone avance por página.
    """

    def log(msg):
        if callback_log:
            callback_log(msg)
        else:
            print(msg)

    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pdf_path = os.path.abspath(os.path.expanduser(pdf_path))
    output_dir = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(output_dir, exist_ok=True)

    if os.path.isdir(pdf_path):
        archivos = sorted(
            glob.glob(os.path.join(pdf_path, "*.pdf")) + glob.glob(os.path.join(pdf_path, "*.epub"))
        )
        if not archivos:
            log(f"⚠ No hay archivos .pdf/.epub en {pdf_path}")
            return
        log(f"📚 {len(archivos)} archivo(s) encontrados en {pdf_path}")
    elif os.path.isfile(pdf_path):
        archivos = [pdf_path]
    else:
        raise FileNotFoundError(f"No existe: {pdf_path}")

    log("🚀 Iniciando conversión con Docling (puede tardar según el tamaño)...")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_picture_images = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )

    ok, fallidos = 0, 0
    for archivo in archivos:
        try:
            _convertir_uno(converter, archivo, output_dir, log, on_progress=on_progress)
            ok += 1
        except Exception as e:
            fallidos += 1
            log(f"❌ Error con {os.path.basename(archivo)}: {e}")

    log(f"📊 Conversión terminada — {ok} OK, {fallidos} con error → {output_dir}/")


def listar(base_dir: str = RUTA_MANUALES_MD):
    """Lista los .md ya convertidos en una carpeta, más recientes primero."""
    base_dir = os.path.abspath(os.path.expanduser(base_dir))
    if not os.path.isdir(base_dir):
        return []
    items = [
        {
            "name": os.path.splitext(os.path.basename(f))[0],
            "path": f,
            "size": os.path.getsize(f),
            "mtime": os.path.getmtime(f),
        }
        for f in glob.glob(os.path.join(base_dir, "*.md"))
    ]
    return sorted(items, key=lambda i: i["mtime"], reverse=True)


def buscar(base_dir: str, query: str, max_por_archivo: int = 5):
    """Busca `query` (texto plano) en todos los .md de base_dir. Devuelve coincidencias por archivo con snippet."""
    base_dir = os.path.abspath(os.path.expanduser(base_dir))
    query = query.strip()
    if not query or not os.path.isdir(base_dir):
        return []

    q_lower = query.lower()
    resultados = []
    for f in sorted(glob.glob(os.path.join(base_dir, "*.md"))):
        coincidencias = []
        try:
            with open(f, encoding="utf-8") as fh:
                for i, linea in enumerate(fh, start=1):
                    idx = linea.lower().find(q_lower)
                    if idx == -1:
                        continue
                    snippet = linea.strip()
                    if len(snippet) > 160:
                        start = max(0, idx - 60)
                        snippet = ("…" if start > 0 else "") + snippet[start:start + 160] + "…"
                    coincidencias.append({"linea": i, "texto": snippet})
                    if len(coincidencias) >= max_por_archivo:
                        break
        except (OSError, UnicodeDecodeError):
            continue
        if coincidencias:
            resultados.append({
                "name": os.path.splitext(os.path.basename(f))[0],
                "path": f,
                "coincidencias": coincidencias,
            })
    return resultados


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convertir PDF(s) a Markdown con Docling")
    parser.add_argument("pdf", help="Ruta a un .pdf o a una carpeta con varios")
    parser.add_argument("-o", "--output", default=RUTA_MANUALES_MD, help="Carpeta de salida")
    args = parser.parse_args()

    print("\n📄 Conversor PDF → Markdown (Docling)\n")
    convertir(args.pdf, output_dir=args.output)
