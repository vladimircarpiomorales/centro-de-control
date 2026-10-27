"""
Centro de Control PRO — main.py
Arranca Flask en un thread y abre PyWebView como ventana nativa.
Instalar: pip install flask flask-socketio pywebview psutil plyer pystray pillow
"""

import os
# Apagar aceleración por hardware para evitar Violación de Segmento en Linux/Wayland
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from dotenv import load_dotenv
load_dotenv()

import json
import socket
import time
import threading
import webview
import pystray
from PIL import Image, ImageDraw
from api import create_app, socketio

FLASK_PORT = int(os.environ.get("FLASK_PORT", 7788))

class JsBridge:
    def hide_window(self):
        try:
            w = webview.windows[0]
            w.hide()
        except Exception:
            pass

    def pick_file(self, file_types=None):
        """Diálogo nativo (GTK) para elegir un archivo. file_types ej: ['PDF files (*.pdf)']."""
        try:
            w = webview.windows[0]
            result = w.create_file_dialog(webview.FileDialog.OPEN, file_types=tuple(file_types or ()))
            return result[0] if result else None
        except Exception:
            return None

    def pick_folder(self):
        """Diálogo nativo (GTK) para elegir una carpeta."""
        try:
            w = webview.windows[0]
            result = w.create_file_dialog(webview.FileDialog.FOLDER)
            return result[0] if result else None
        except Exception:
            return None

def create_tray_icon(window):
    """Crea un ícono en el system tray para minimizar/restaurar."""
    img = Image.new("RGB", (64, 64), color="#0a0c10")
    draw = ImageDraw.Draw(img)
    draw.ellipse([16, 16, 48, 48], fill="#00ffc8")

    def on_show(icon, item):
        window.show()
        window.restore()

    def on_quit(icon, item):
        icon.stop()
        window.destroy()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar panel", on_show, default=True),
        pystray.MenuItem("Salir", on_quit),
    )
    return pystray.Icon("CentroControlPRO", img, "Centro de Control PRO", menu)

# ─── Tamaño de la ventana ─────────────────────────────────────────────────────
# Se guarda al redimensionar y se recupera al abrir. En Wayland la posición la
# decide KWin (la app no puede fijarla), así que solo se guardan tamaño y
# maximizado.
VENTANA_FILE = os.path.expanduser("~/.local/share/mipanelcontrol/ventana.json")
VENTANA_DEF  = {"width": 980, "height": 720, "maximized": False}
MIN_SIZE     = (800, 600)

def cargar_ventana() -> dict:
    try:
        with open(VENTANA_FILE) as f:
            v = {**VENTANA_DEF, **json.load(f)}
        v["width"]  = max(MIN_SIZE[0], int(v["width"]))
        v["height"] = max(MIN_SIZE[1], int(v["height"]))
        return v
    except Exception:
        return dict(VENTANA_DEF)

def vigilar_ventana(window, estado: dict):
    temporizador = [None]

    def guardar():
        try:
            os.makedirs(os.path.dirname(VENTANA_FILE), exist_ok=True)
            tmp = VENTANA_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(estado, f)
            os.replace(tmp, VENTANA_FILE)
        except Exception:
            pass

    def programar():
        # al arrastrar el borde llegan decenas de eventos: se escribe 1 s después del último
        if temporizador[0]:
            temporizador[0].cancel()
        temporizador[0] = threading.Timer(1.0, guardar)
        temporizador[0].daemon = True
        temporizador[0].start()

    def maximizada() -> bool:
        try:
            return bool(window.native.is_maximized())
        except Exception:
            return estado["maximized"]

    def on_resized(width, height):
        estado["maximized"] = maximizada()
        # el tamaño maximizado no es el que se quiere recuperar al desmaximizar
        if not estado["maximized"] and width >= MIN_SIZE[0] and height >= MIN_SIZE[1]:
            estado["width"], estado["height"] = width, height
        programar()

    def on_maximized():
        estado["maximized"] = True
        programar()

    def on_restored():
        estado["maximized"] = maximizada()
        programar()

    window.events.resized += on_resized
    window.events.maximized += on_maximized
    window.events.restored += on_restored
    window.events.closing += guardar

def run_flask(app):
    socketio.run(app, host="127.0.0.1", port=FLASK_PORT, use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)

def _wait_for_flask(host="127.0.0.1", port=FLASK_PORT, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)


if __name__ == "__main__":
    app = create_app()

    # 1. Iniciar Flask en un thread daemon
    flask_thread = threading.Thread(target=run_flask, args=(app,), daemon=True)
    flask_thread.start()
    _wait_for_flask()

    # 2. Crear ventana PyWebView
    js_api = JsBridge()
    ventana = cargar_ventana()
    window = webview.create_window(
        title="Centro de Control PRO",
        url=f"http://127.0.0.1:{FLASK_PORT}",
        width=ventana["width"],
        height=ventana["height"],
        maximized=ventana["maximized"],
        resizable=True,
        min_size=MIN_SIZE,
        background_color="#0a0c10",
        frameless=False,
        easy_drag=False,
        js_api=js_api,
    )

    # 3. Preparar Tray Icon SIN loop propio — comparte el main loop de GTK
    #    que arranca webview.start() más abajo. Antes corría en su propio
    #    thread con tray.run(), y competía por el mismo main context de
    #    GLib contra el de PyWebView (carrera de hilos → fallaba al azar
    #    con "cannot acquire the default main context").
    vigilar_ventana(window, ventana)
    tray = create_tray_icon(window)
    tray.run_detached()

    # 4. Loop principal de la UI (bloqueante) — único main loop del proceso
    # private_mode=False + carpeta propia: sin esto localStorage se pierde al
    # cerrar y no se recuerdan el tamaño de letra, la terminal plegada, etc.
    webview.start(debug=False, gui="gtk", private_mode=False,
                  storage_path=os.path.expanduser("~/.local/share/mipanelcontrol/webview"))
