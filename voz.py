"""
Centro de Control PRO — voz.py
Voz del panel: leer texto en voz alta (Piper, local) y pasar tu voz a texto
(Whisper de Groq a través de OmniRoute).

  sintetizar(texto, idioma)  → ruta a un WAV en caché (es: es_ES-davefx, en: en_US-lessac)
  Grabadora                  → graba el micrófono por defecto con pw-record (PipeWire)
  transcribir(wav, idioma)   → texto. La grabación sale del equipo hacia Groq (vía
                               OmniRoute); Groq no entrena con lo que recibe por API.
"""

import hashlib
import json
import os
import signal
import subprocess
import threading
import time
import urllib.request
import uuid

VOZ_DIR   = os.path.expanduser(os.environ.get("PIPER_DIR", "~/.local/share/piper"))
VOCES     = {"es": os.environ.get("VOZ_ES", "es_ES-davefx-medium"),
             "en": os.environ.get("INGLES_VOZ", "en_US-lessac-medium")}
CACHE     = os.path.expanduser("~/.cache/mipanelcontrol/voz")
WHISPER   = os.environ.get("WHISPER_MODELO", "groq/whisper-large-v3-turbo")
OMNIROUTE = os.environ.get("OMNIROUTE_URL", "http://127.0.0.1:20128/v1/chat/completions").rsplit("/v1/", 1)[0]
_modelos  = {}
_lock     = threading.Lock()


def sintetizar(texto: str, idioma: str = "es") -> str:
    voz = VOCES.get(idioma, VOCES["es"])
    ruta = os.path.join(CACHE, hashlib.sha1(f"{voz}|{texto}".encode()).hexdigest()[:16] + ".wav")
    if os.path.isfile(ruta):
        return ruta
    import wave
    with _lock:
        if voz not in _modelos:
            from piper import PiperVoice
            _modelos[voz] = PiperVoice.load(os.path.join(VOZ_DIR, voz + ".onnx"))
        os.makedirs(CACHE, exist_ok=True)
        tmp = ruta + ".tmp"
        with wave.open(tmp, "wb") as w:
            _modelos[voz].synthesize_wav(texto, w)
        os.replace(tmp, ruta)
    return ruta


class Grabadora:
    """Una sola grabación a la vez. Se corta sola a los MAX_SEG por si se olvida."""
    MAX_SEG = 240

    def __init__(self):
        self.proc, self.ruta, self.inicio = None, None, 0

    def grabando(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def empezar(self, ruta: str):
        if self.grabando():
            self.parar()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        self.ruta, self.inicio = ruta, time.time()
        self.proc = subprocess.Popen(["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", ruta],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc = self.proc
        threading.Timer(self.MAX_SEG, lambda: proc.poll() is None and proc.send_signal(signal.SIGINT)).start()

    def parar(self) -> tuple:
        """Devuelve (ruta, segundos). pw-record cierra bien el WAV con SIGINT."""
        if not self.proc:
            return None, 0
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        segundos = round(time.time() - self.inicio)
        ruta, self.proc = self.ruta, None
        return ruta, segundos


# Whisper acierta mucho más con los nombres técnicos si se los das de pista
PISTA = ("VMware, vSphere, ESXi, Azure, Entra ID, Active Directory, Linux, Debian, Windows Server, Aruba, "
         "ClearPass, Cisco, VLAN, 802.1X, RADIUS, BGP, IPv6, Podman, Docker, PowerShell, Bash, Python, "
         "Cloudflare, Google Workspace, Microsoft 365, AZ-104, CCNA, LPIC, troubleshooting, on-call.")

def nivel(ruta: str) -> float:
    """Volumen medio (RMS, 0-32768) de un WAV de 16 bits. Whisper se inventa frases («Gracias.»)
    cuando le llega silencio, así que antes de transcribir se mira si hay voz."""
    import array
    import math
    import wave
    with wave.open(ruta, "rb") as w:
        datos = array.array("h", w.readframes(w.getnframes()))
    if not datos:
        return 0.0
    return math.sqrt(sum(x * x for x in datos[::4]) / len(datos[::4]))

def transcribir(ruta: str, idioma: str = "es") -> str:
    clave = os.environ.get("OMNIROUTE_API_KEY", "")
    if not clave:
        raise RuntimeError("falta OMNIROUTE_API_KEY en .env")
    frontera = uuid.uuid4().hex
    with open(ruta, "rb") as f:
        audio = f.read()
    partes = []
    for nombre, valor in (("model", WHISPER), ("language", idioma), ("response_format", "json"), ("prompt", PISTA)):
        partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="{nombre}"\r\n\r\n{valor}\r\n'.encode())
    partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="file"; filename="voz.wav"\r\n'
                  f'Content-Type: audio/wav\r\n\r\n'.encode() + audio + b"\r\n")
    cuerpo = b"".join(partes) + f"--{frontera}--\r\n".encode()
    pet = urllib.request.Request(OMNIROUTE + "/v1/audio/transcriptions", data=cuerpo, method="POST", headers={
        "Authorization": f"Bearer {clave}", "Content-Type": f"multipart/form-data; boundary={frontera}"})
    with urllib.request.urlopen(pet, timeout=120) as r:
        d = json.load(r)
    if d.get("error"):
        raise RuntimeError(str(d["error"])[:200])
    return (d.get("text") or "").strip()
