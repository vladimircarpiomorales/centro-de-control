"""Cola de trabajos para la IA local: aprovecha la GPU mientras no la usas.

Un trabajo solo se ejecuta si el portátil está enchufado, no hay videollamada
(cámara o micrófono en uso) y la GPU tiene hueco para el modelo. Si Ollama
estaba apagado lo enciende para la tanda y al acabar lo vuelve a apagar.
"""
import glob
import json
import subprocess
import threading
import time
import urllib.request

from status import log
from rag import OLLAMA_URL
from services import RUTA_OLLAMA_SCRIPT

ESPERA        = 5 * 60   # cada cuánto se vuelve a mirar si se puede trabajar
VRAM_NECESARIA = 3500     # MiB que pide qwen3.5:4b con contexto 8192
_cola         = {}       # clave → (que, fn); un dict para no encolar dos veces lo mismo
_cerrojo      = threading.Lock()
_hay_trabajo  = threading.Event()


def encolar(clave: str, que: str, fn) -> bool:
    """Apunta un trabajo. Si ya había uno con esa clave, no se duplica."""
    with _cerrojo:
        if clave in _cola:
            return False
        _cola[clave] = (que, fn)
    _hay_trabajo.set()
    return True

def pendientes() -> list:
    with _cerrojo:
        return [que for que, _ in _cola.values()]


# ─── ¿Se puede trabajar ahora? ─────────────────────────────────────────────────
def _enchufado() -> bool:
    for f in glob.glob("/sys/class/power_supply/A*/online"):   # AC, ACAD, ADP1…
        try:
            if open(f).read().strip() == "1":
                return True
        except OSError:
            pass
    # sin cargador detectable (sobremesa): se da por enchufado
    return not glob.glob("/sys/class/power_supply/BAT*")

def _en_llamada() -> bool:
    """Cámara abierta o alguien grabando el micro = videollamada (Zoom, Webex, Meet…)."""
    camaras = glob.glob("/dev/video*")
    if camaras and subprocess.run(["fuser", *camaras], capture_output=True).returncode == 0:
        return True
    r = subprocess.run(["pactl", "list", "source-outputs", "short"], capture_output=True, text=True)
    return bool(r.stdout.strip())

def _vram_libre() -> int:
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0])
    except (IndexError, ValueError):
        return 0

def _ollama_vivo() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3).read()
        return True
    except Exception:
        return False

def _modelo_cargado() -> bool:
    try:
        return bool(json.loads(urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=3).read())["models"])
    except Exception:
        return False

def motivo_espera() -> str:
    """Vacío si se puede trabajar; si no, el porqué (para el log)."""
    if not _enchufado():
        return "con batería"
    if _en_llamada():
        return "en videollamada"
    # con un modelo ya cargado la VRAM se ve ocupada por Ollama mismo: eso no cuenta
    if _vram_libre() < VRAM_NECESARIA and not (_ollama_vivo() and _modelo_cargado()):
        return "GPU ocupada"
    return ""


# ─── Encender y apagar Ollama ──────────────────────────────────────────────────
def _encender() -> bool:
    subprocess.run([RUTA_OLLAMA_SCRIPT], capture_output=True, timeout=60)
    for _ in range(30):
        if _ollama_vivo():
            return True
        time.sleep(1)
    return False

def _apagar():
    # si mientras tanto abriste Open WebUI, el motor se queda para el chat
    r = subprocess.run(["podman", "container", "inspect", "-f", "{{.State.Running}}", "openwebui"],
                       capture_output=True, text=True)
    if r.stdout.strip() == "true":
        return False
    from actions import _quitar
    _quitar("ollama")
    return True


# ─── El bucle ──────────────────────────────────────────────────────────────────
def _tanda():
    motivo = motivo_espera()
    if motivo:
        log(f"🤖 Cola IA: {len(_cola)} trabajo(s) esperando ({motivo})")
        return
    encendido_por_mi = not _ollama_vivo()
    if encendido_por_mi:
        log("🤖 Cola IA: enciendo Ollama para los trabajos pendientes")
        if not _encender():
            log("⚠ Cola IA: Ollama no arrancó; lo reintento más tarde")
            return
    try:
        while True:
            with _cerrojo:
                if not _cola:
                    break
                clave = next(iter(_cola))
                que, fn = _cola[clave]
            if motivo_espera():   # p. ej. empezó una llamada a mitad de tanda
                log("🤖 Cola IA: pausa, el equipo se necesita para otra cosa")
                break
            log(f"🤖 Cola IA: {que}")
            try:
                fn()
            except Exception as e:
                log(f"⚠ Cola IA: «{que}» falló: {e}")
            with _cerrojo:
                _cola.pop(clave, None)
    finally:
        if encendido_por_mi and _apagar():
            log("🤖 Cola IA: hecho, Ollama apagado otra vez")

def _bucle():
    while True:
        _hay_trabajo.wait()
        _tanda()
        with _cerrojo:
            if not _cola:
                _hay_trabajo.clear()
                continue
        time.sleep(ESPERA)

def start_cola():
    threading.Thread(target=_bucle, daemon=True).start()
