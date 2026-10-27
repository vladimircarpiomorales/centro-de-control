"""
Conversor EPUB → M4B usando audiblez dentro de contenedor Podman.
"""

import os
import re
import subprocess
import shlex

VOICES_DISPONIBLES = {
    "af_sky":     "🇺🇸 EN-US Sky",
    "af_bella":   "🇺🇸 EN-US Bella",
    "af_nicole":  "🇺🇸 EN-US Nicole",
    "am_adam":    "🇺🇸 EN-US Adam",
    "am_michael": "🇺🇸 EN-US Michael",
    "am_onyx":    "🇺🇸 EN-US Onyx",
    "bf_emma":    "🇬🇧 EN-UK Emma",
    "bm_daniel":  "🇬🇧 EN-UK Daniel",
    "ef_dora":    "🇪🇸 ES Dora",
    "em_alex":    "🇪🇸 ES Alex",
    "ff_siwis":   "🇫🇷 FR Siwis",
    "if_sara":    "🇮🇹 IT Sara",
    "im_nicola":  "🇮🇹 IT Nicola",
    "jf_alpha":   "🇯🇵 JP Alpha",
}


def convertir(epub_path: str, voz: str = "ef_dora", velocidad: float = 1.0,
              output_dir: str = "~/Audiolibros", callback_log=None):
    """Convierte .epub a .m4b usando audiblez en contenedor Podman."""

    def log(msg):
        if callback_log:
            callback_log(msg)
        else:
            print(msg)

    epub_path = os.path.abspath(os.path.expanduser(epub_path))
    output_dir = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(epub_path):
        raise FileNotFoundError(f"No existe: {epub_path}")

    nombre = os.path.splitext(os.path.basename(epub_path))[0]
    nombre = re.sub(r'[^\w\- ]', '', nombre).strip() or "audiolibro"

    epub_dir = os.path.dirname(epub_path)
    epub_file = os.path.basename(epub_path)

    log(f"📖 Convirtiendo {epub_file} → {output_dir}/")
    log(f"🔊 Voz: {voz} | Velocidad: {velocidad}x")

    cmd = [
        "podman", "run", "--rm",
        "--device", "nvidia.com/gpu=all",
        "--cpus", "2",
        "-v", f"{epub_dir}:/input:ro,Z",
        "-v", f"{output_dir}:/output:Z",
        "audiolibro:latest",
        f"/input/{epub_file}",
        "-v", voz,
        "-s", str(velocidad),
        "-o", "/output",
        "--cuda",
    ]

    log(f"🚀 Iniciando conversión...")

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1)

        # Leer stdout en tiempo real
        for line in iter(process.stdout.readline, ""):
            line = line.rstrip()
            if line:
                log(f"  {line}")
        process.stdout.close()

        # Leer stderr restante
        for line in process.stderr:
            line = line.rstrip()
            if line and "WARNING" not in line and "INFO" not in line:
                log(f"  ⚠ {line}")
        process.stderr.close()

        process.wait(timeout=3600)

        if process.returncode != 0:
            raise RuntimeError(f"Error audiblez (código {process.returncode})")

        # Buscar archivo .m4b generado
        m4b_path = None
        for f in os.listdir(output_dir):
            if f.endswith(".m4b"):
                m4b_path = os.path.join(output_dir, f)
                break

        if m4b_path:
            tamano = os.path.getsize(m4b_path)
            log(f"✅ Audiolibro listo: {os.path.basename(m4b_path)} ({tamano // 1024 // 1024} MB)")
        else:
            log("⚠ Los WAV están generados pero no se creó el .m4b. Combinando manualmente...")
            _combinar_wavs(output_dir, os.path.basename(epub_path).replace(".epub", ""))

    except subprocess.TimeoutExpired:
        raise RuntimeError("⏱ Tiempo de conversión agotado (> 1 hora)")

def _combinar_wavs(output_dir: str, nombre_base: str):
    """Combina WAVs en .m4b si audiblez no lo hizo."""
    import glob
    wavs = sorted(glob.glob(os.path.join(output_dir, "*.wav")))
    if not wavs:
        return
    m4b_path = os.path.join(output_dir, f"{nombre_base}.m4b")
    lista = os.path.join(output_dir, "_files.txt")
    with open(lista, "w") as f:
        for w in wavs:
            f.write(f"file '{w}'\n")
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", lista,
                        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                        "-metadata", f"title={nombre_base}",
                        m4b_path],
                       capture_output=True, text=True, timeout=600)
    os.remove(lista)
    if os.path.exists(m4b_path):
        tamano = os.path.getsize(m4b_path)
        log(f"✅ Audiolibro creado manualmente: {os.path.basename(m4b_path)} ({tamano // 1024 // 1024} MB)")
    else:
        log(f"❌ Error al combinar WAVs: {r.stderr[:200]}")


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convertir EPUB a audiolibro M4B")
    parser.add_argument("epub", help="Ruta al archivo .epub")
    parser.add_argument("-v", "--voz", default="ef_dora",
                        choices=list(VOICES_DISPONIBLES.keys()),
                        help="Voz para narrar")
    parser.add_argument("-s", "--speed", type=float, default=1.0,
                        help="Velocidad (0.5-2.0)")
    parser.add_argument("-o", "--output", default="~/Audiolibros",
                        help="Carpeta de salida")
    args = parser.parse_args()

    print("\n📚 Conversor EPUB → M4B (via audiblez en contenedor)\n")
    convertir(args.epub, voz=args.voz, velocidad=args.speed, output_dir=args.output)
