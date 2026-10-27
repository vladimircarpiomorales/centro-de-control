"""
Centro de Control PRO — api.py
Orquestador: importa módulos y expone create_app + socketio para main.py.
"""

import os
import re
import time
import subprocess
import webbrowser
from urllib.parse import quote
from flask import Flask, jsonify, render_template, request, send_file

from extensions import socketio                                    # re-exportado para main.py
from services  import SERVICES, RUTA_METUBE_DIR, RUTA_MANUALES_MD
from status    import (get_all_statuses, get_system_stats, get_health_statuses,
                       get_uptimes, log, run_bg, _log_buffer, start_notification_monitor)
from actions   import _toggle, _do_update, _restart
import becas
import carrera
import ofertas
import cola_ia
import ingles
import candidatura
import laboratorios
import copias
import mantenimiento
import estudio
import entrevistas
import redes
import sueldo
import agenda
import contactos
import foco
import retos
import tarjetas
import resumen


FLASK_PORT = int(os.environ.get("FLASK_PORT", 7788))
HOSTS_PERMITIDOS = {f"127.0.0.1:{FLASK_PORT}", f"localhost:{FLASK_PORT}"}
# la extensión de descargas (extension-metube), cargada desempaquetada en Brave
EXTENSION_ID = os.environ.get("EXTENSION_ID", "")   # extensión de descargas cargada en Brave/Chrome
ORIGENES_PERMITIDOS = {f"http://{h}" for h in HOSTS_PERMITIDOS} | ({f"chrome-extension://{EXTENSION_ID}"} if EXTENSION_ID else set())


def create_app():
    app = Flask(__name__, template_folder="ui", static_folder="ui/static")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "centrocontrolpro")
    socketio.init_app(app)
    start_notification_monitor()
    becas.start_becas_monitor()
    ofertas.start_ofertas_monitor()
    cola_ia.start_cola()
    ingles.start_audio_precalentar()
    copias.start_copias()
    mantenimiento.start_mantenimiento()
    redes.start_vigilante()
    agenda.start_agenda()
    foco.start_foco()
    resumen.start_resumen()

    # ── Solo el propio panel y la extensión de Brave pueden dar órdenes ──────
    # Sin esto, cualquier web abierta en el navegador podía mandar POST a
    # 127.0.0.1:7788 (mover archivos, apagar servicios…) y, con DNS rebinding,
    # leer ficheros de $HOME. Host fijo corta el rebinding; Origin, el resto.
    @app.before_request
    def _solo_local():
        host = (request.host or "").lower()
        if host not in HOSTS_PERMITIDOS:
            return jsonify({"error": "Host no permitido"}), 403
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origen = request.headers.get("Origin")
            # sin Origin = curl o scripts locales; los navegadores siempre lo mandan
            if origen and origen not in ORIGENES_PERMITIDOS:
                return jsonify({"error": "Origen no permitido"}), 403

    @app.context_processor
    def _asset_version():
        # cambia cuando se edita cualquier CSS/JS → el webview no se queda con la copia vieja
        base = os.path.join(app.root_path, "ui", "static")
        mt = [os.path.getmtime(os.path.join(r, f)) for d in ("css", "js")
              for r, _, fs in os.walk(os.path.join(base, d)) for f in fs]
        return {"asset_v": int(max(mt, default=0))}

    @app.route("/")
    def index():
        return render_template("index.html", services=SERVICES, manuales_dir=RUTA_MANUALES_MD)

    @app.route("/manuales")
    def manuales_page():
        return render_template("manuales.html", manuales_dir=RUTA_MANUALES_MD)

    @app.route("/api/status")
    def api_status():
        running = get_all_statuses()
        return jsonify({
            "services": running,
            "system":   get_system_stats(),
            "health":   get_health_statuses(running),
            "uptimes":  get_uptimes(running),
        })

    @app.route("/api/toggle/<service_id>", methods=["POST"])
    def api_toggle(service_id):
        if service_id not in SERVICES:
            return jsonify({"error": "Servicio desconocido"}), 404
        data   = request.get_json(force=True)
        action = "start" if data.get("on") else "stop"
        run_bg(lambda: _toggle(service_id, action), clave=f"servicio:{service_id}", que=SERVICES[service_id]["label"])
        return jsonify({"ok": True})

    @app.route("/api/update/<service_id>", methods=["POST"])
    def api_update(service_id):
        if service_id not in SERVICES:
            return jsonify({"error": "Servicio desconocido"}), 404
        run_bg(lambda: _do_update(service_id), clave=f"servicio:{service_id}", que=SERVICES[service_id]["label"])
        return jsonify({"ok": True})

    @app.route("/api/restart/<service_id>", methods=["POST"])
    def api_restart(service_id):
        if service_id not in SERVICES:
            return jsonify({"error": "Servicio desconocido"}), 404
        run_bg(lambda: _restart(service_id), clave=f"servicio:{service_id}", que=SERVICES[service_id]["label"])
        return jsonify({"ok": True})

    @app.route("/api/metube/queue")
    def api_metube_queue():
        import json
        queue, completed = [], []
        try:
            with open(os.path.join(RUTA_METUBE_DIR, "queue.json")) as f:
                queue = json.load(f).get("items", [])
        except Exception:
            pass
        try:
            with open(os.path.join(RUTA_METUBE_DIR, "completed.json")) as f:
                items = json.load(f).get("items", [])
                completed = sorted(items, key=lambda x: x.get("info", {}).get("timestamp", 0), reverse=True)[:5]
        except Exception:
            pass
        return jsonify({"queue": queue, "completed": completed})

    @app.route("/api/descargas/sonda", methods=["POST"])
    def api_descargas_sonda():
        # Síncrona a propósito: quien pregunta (la extensión de Brave) necesita el
        # veredicto para decidir. Con async_mode="threading" solo ocupa su hilo.
        import sonda
        data = request.get_json(force=True, silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Falta la url"}), 400
        return jsonify(sonda.probar(url))

    @app.route("/api/descargas/sitios")
    def api_descargas_sitios():
        # La extensión la pide una vez al día para mantener su lista al día sin
        # que haya que reinstalarla. ?forzar=1 salta la caché de una hora.
        import sitios
        datos = sitios.listar(forzar=request.args.get("forzar") == "1")
        return jsonify(datos), (500 if datos.get("error") else 200)

    @app.route("/api/file-size", methods=["POST"])
    def api_file_size():
        data = request.get_json(force=True, silent=True) or {}
        path = data.get("path", "")
        if path and os.path.isfile(path):
            return jsonify({"size": os.path.getsize(path)})
        return jsonify({"size": 0})

    @app.route("/api/pick-file", methods=["POST"])
    def api_pick_file():
        data = request.get_json(force=True, silent=True) or {}
        ext = data.get("ext", "epub").lower().lstrip(".")
        label = {"epub": "EPUB files", "pdf": "PDF files"}.get(ext, f"{ext.upper()} files")
        for candidate in [
            ["kdialog", "--getopenfilename", "", f"*.{ext}"],
            ["zenity",  "--file-selection", "--file-filter", f"{label} | *.{ext}"],
        ]:
            try:
                r = subprocess.run(candidate, capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and r.stdout.strip():
                    return jsonify({"path": r.stdout.strip()})
            except (FileNotFoundError, Exception):
                continue
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(filetypes=[(label, f"*.{ext}")])
            root.destroy()
            if path:
                return jsonify({"path": path})
        except Exception:
            pass
        return jsonify({"path": None, "error": "No se pudo abrir el selector"}), 500

    @app.route("/api/pick-folder", methods=["POST"])
    def api_pick_folder():
        for candidate in [
            ["kdialog", "--getexistingdirectory"],
            ["zenity",  "--file-selection", "--directory"],
        ]:
            try:
                r = subprocess.run(candidate, capture_output=True, text=True, timeout=30)
                if r.returncode == 0 and r.stdout.strip():
                    return jsonify({"path": r.stdout.strip()})
            except (FileNotFoundError, Exception):
                continue
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory()
            root.destroy()
            if path:
                return jsonify({"path": path})
        except Exception:
            pass
        return jsonify({"path": None, "error": "No se pudo abrir el selector de carpetas"}), 500

    @app.route("/api/organize", methods=["POST"])
    def api_organize():
        data         = request.get_json(force=True, silent=True) or {}
        dry_run      = data.get("dry_run", True)
        origenes     = data.get("origenes", ["~/Descargas", "~/Desktop"])
        destino_base = os.path.expanduser(data.get("destino", "~/Organizado"))

        from organizador import escanear, organizar

        def worker():
            log("🔍 Escaneando archivos para organizar...")
            resultados = escanear(origenes, usar_ia=True)
            if not resultados:
                log("📭 No se encontraron archivos.")
                return
            for r in resultados:
                r["destino"] = os.path.join(destino_base, r["categoria"])
            por_cat = {}
            for r in resultados:
                por_cat.setdefault(r["categoria"], []).append(r)
            for cat, items in sorted(por_cat.items()):
                log(f"  {cat}: {len(items)} archivos")
            log(f"📊 Total: {len(resultados)} archivos")
            if dry_run:
                log(f"🔍 Vista previa → {destino_base}/")
            else:
                log(f"🚀 Moviendo archivos a {destino_base}/...")
                resumen = organizar(resultados, dry_run=False)
                if resumen["errores"]:
                    log(f"❌ {resumen['errores']} errores")
                log(f"✅ {resumen['movidos']} archivos organizados")

        run_bg(worker, clave="organizar", que="Organizar descargas")
        return jsonify({"ok": True})

    @app.route("/api/convert-epub", methods=["POST"])
    def api_convert_epub():
        data       = request.get_json(force=True, silent=True) or {}
        epub_path  = data.get("epub_path", "")
        voz        = data.get("voz", "ef_dora")
        velocidad  = float(data.get("velocidad", 1.0))
        output_dir = data.get("output_dir", "~/Audiolibros")

        if not epub_path:
            return jsonify({"ok": False, "error": "Falta epub_path"}), 400

        from audiolibro import convertir

        def worker():
            try:
                convertir(epub_path, voz=voz, velocidad=velocidad,
                          output_dir=output_dir, callback_log=log)
            except Exception as e:
                log(f"❌ Error: {e}")

        run_bg(worker, clave="audiolibro", que="La conversión a audiolibro")
        return jsonify({"ok": True})

    @app.route("/api/convert-pdf", methods=["POST"])
    def api_convert_pdf():
        data       = request.get_json(force=True, silent=True) or {}
        pdf_path   = data.get("pdf_path", "")
        output_dir = data.get("output_dir", RUTA_MANUALES_MD)

        if not pdf_path:
            return jsonify({"ok": False, "error": "Falta pdf_path"}), 400

        from pdf2md import convertir

        def on_progress(nombre, pct):
            socketio.emit("pdf_progress", {"file": nombre, "percent": pct})

        def worker():
            try:
                convertir(pdf_path, output_dir=output_dir, callback_log=log, on_progress=on_progress)
            except Exception as e:
                log(f"❌ Error: {e}")

        run_bg(worker, clave="pdf2md", que="La conversión de PDF")
        return jsonify({"ok": True})

    @app.route("/api/manuales/open-browser", methods=["POST"])
    def api_manuales_open_browser():
        url = request.host_url + "manuales"
        # Modo app (sin pestañas/barra de direcciones) — se ve tan compacto como el
        # panel nativo, pero usa el motor Chromium (mucho más rápido que WebKitGTK
        # para documentos grandes). Si no hay Brave, cae a abrir en el navegador normal.
        for candidate in ["brave-browser", "brave"]:
            try:
                subprocess.Popen([candidate, f"--app={url}"])
                return jsonify({"ok": True})
            except FileNotFoundError:
                continue
        try:
            webbrowser.open(url)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/manuales")
    def api_manuales_list():
        from pdf2md import listar
        base_dir = _dir_manuales(request.args.get("dir"))
        if not base_dir:
            return jsonify({"error": "Carpeta no permitida"}), 400
        return jsonify({"items": listar(base_dir)})

    def _ruta_manuales_permitida(path: str) -> bool:
        # El vault de Obsidian (donde caen los manuales convertidos) puede vivir fuera de
        # $HOME (ej. en un mount de OneDrive), así que además de $HOME permitimos la
        # carpeta de manuales configurada. Se compara la ruta real carpeta a carpeta
        # (commonpath), no el texto: con startswith, /home/ana2 pasaba por /home/ana.
        path = os.path.realpath(os.path.expanduser(path or ""))
        for raiz in (os.path.expanduser("~"), RUTA_MANUALES_MD):
            raiz = os.path.realpath(raiz)
            if os.path.commonpath([path, raiz]) == raiz:
                return True
        return False

    def _dir_manuales(valor):
        """La carpeta de manuales que pide el cliente, si es válida; si no, None."""
        d = os.path.realpath(os.path.expanduser(valor or RUTA_MANUALES_MD))
        return d if _ruta_manuales_permitida(d) else None

    @app.route("/api/manuales/buscar")
    def api_manuales_buscar():
        from pdf2md import buscar
        base_dir = _dir_manuales(request.args.get("dir"))
        if not base_dir:
            return jsonify({"error": "Carpeta no permitida"}), 400
        q = request.args.get("q", "")
        return jsonify({"resultados": buscar(base_dir, q)})

    @app.route("/api/manuales/rag/index", methods=["POST"])
    def api_manuales_rag_index():
        from rag import indexar
        data = request.get_json(force=True, silent=True) or {}
        base_dir = _dir_manuales(data.get("dir"))
        if not base_dir:
            return jsonify({"error": "Carpeta no permitida"}), 400

        def worker():
            try:
                indexar(base_dir, callback_log=log)
            except Exception as e:
                log(f"❌ Error indexando RAG: {e}")

        run_bg(worker, clave="rag_index", que="La indexación de manuales")
        return jsonify({"ok": True})

    @app.route("/api/manuales/rag/ask", methods=["POST"])
    def api_manuales_rag_ask():
        from rag import preguntar
        data = request.get_json(force=True, silent=True) or {}
        pregunta = data.get("pregunta", "").strip()
        base_dir = _dir_manuales(data.get("dir"))
        modelo = data.get("modelo", "llama3.1")
        if not base_dir:
            return jsonify({"error": "Carpeta no permitida"}), 400
        if not pregunta:
            return jsonify({"error": "Falta la pregunta"}), 400
        try:
            resultado = preguntar(pregunta, base_dir=base_dir, modelo=modelo)
            return jsonify(resultado)
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route("/api/manuales/raw")
    def api_manuales_raw():
        path = os.path.realpath(os.path.expanduser(request.args.get("path", "")))
        if (not _ruta_manuales_permitida(path) or not os.path.isfile(path)
                or not path.lower().endswith(".md")):
            return jsonify({"error": "Ruta inválida"}), 400

        with open(path, encoding="utf-8") as f:
            content = f.read()

        base_dir = os.path.dirname(path)

        def _rewrite_img(m):
            alt, src = m.group(1), m.group(2)
            if src.startswith(("http://", "https://", "data:")):
                return m.group(0)
            abs_img = os.path.normpath(os.path.join(base_dir, src))
            return f"![{alt}](/api/manuales/img?path={quote(abs_img)})"

        # (.+) en vez de ([^)]+): los nombres de archivo pueden traer paréntesis propios
        # (ej. "... (HPE6-A72)_img/imagen.png") — con [^)]+ el regex cortaba en el primer
        # paréntesis del NOMBRE en vez del que cierra el markdown, truncando la ruta.
        content = re.sub(r"!\[([^\]]*)\]\((.+)\)", _rewrite_img, content)
        return jsonify({"content": content})

    @app.route("/api/manuales/img")
    def api_manuales_img():
        path = os.path.realpath(request.args.get("path", ""))
        if (not _ruta_manuales_permitida(path) or not os.path.isfile(path)
                or not path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))):
            return jsonify({"error": "No encontrado"}), 404
        return send_file(path)

    @app.route("/api/becas")
    def api_becas():
        return jsonify(becas.get_data())

    @app.route("/api/becas/refresh", methods=["POST"])
    def api_becas_refresh():
        data = request.get_json(force=True, silent=True) or {}
        deep = bool(data.get("deep"))
        run_bg(lambda: becas.refresh(deep=deep), clave="becas", que="La búsqueda de becas")
        return jsonify({"ok": True})

    @app.route("/api/becas/vistos", methods=["POST"])
    def api_becas_vistos():
        becas.marcar_vistos()
        return jsonify({"ok": True})

    @app.route("/api/becas/open", methods=["POST"])
    def api_becas_open():
        data = request.get_json(force=True, silent=True) or {}
        url  = data.get("url", "")
        if not url.startswith(("http://", "https://")):
            return jsonify({"error": "URL inválida"}), 400
        webbrowser.open(url)
        return jsonify({"ok": True})

    @app.route("/api/becas/directo", methods=["POST"])
    def api_becas_directo():
        data = request.get_json(force=True, silent=True) or {}
        url  = data.get("url", "")
        if not url.startswith(("http://", "https://")):
            return jsonify({"error": "URL inválida"}), 400

        def worker():
            log("🎯 Buscando enlace directo (saltando redirecciones)...")
            directo = becas.resolver_directo(url)
            if directo:
                log(f"🎯 Enlace directo encontrado → abriendo Udemy")
                webbrowser.open(directo)
            else:
                log("⚠ No encontré enlace directo — abriendo la publicación original")
                webbrowser.open(url)

        run_bg(worker, clave="becas", que="La búsqueda de becas")
        return jsonify({"ok": True})

    @app.route("/api/ofertas")
    def api_ofertas():
        return jsonify(ofertas.get_data())

    @app.route("/api/ofertas/refresh", methods=["POST"])
    def api_ofertas_refresh():
        run_bg(ofertas.refresh, clave="ofertas", que="La búsqueda de ofertas")
        return jsonify({"ok": True})

    @app.route("/api/ofertas/vistas", methods=["POST"])
    def api_ofertas_vistas():
        ofertas.marcar_vistas()
        return jsonify({"ok": True})

    @app.route("/api/ofertas/estado", methods=["POST"])
    def api_ofertas_estado():
        data = request.get_json(force=True, silent=True) or {}
        ok = ofertas.set_estado(data.get("id", ""), data.get("estado", ""))
        return jsonify({"ok": ok})

    @app.route("/api/ofertas/nota", methods=["POST"])
    def api_ofertas_nota():
        data = request.get_json(force=True, silent=True) or {}
        ok = ofertas.set_nota(data.get("id", ""), data.get("nota", ""))
        return jsonify({"ok": ok})

    @app.route("/api/ofertas/descripcion", methods=["POST"])
    def api_ofertas_descripcion():
        data = request.get_json(force=True, silent=True) or {}
        ok = ofertas.set_descripcion(data.get("id", ""), data.get("texto", ""))
        return jsonify({"ok": ok})

    @app.route("/api/ofertas/seguimiento", methods=["POST"])
    def api_ofertas_seguimiento():
        data = request.get_json(force=True, silent=True) or {}
        ok = ofertas.seguimiento_hecho(data.get("id", ""))
        return jsonify({"ok": ok})

    @app.route("/api/ofertas/manual", methods=["POST"])
    def api_ofertas_manual():
        data = request.get_json(force=True, silent=True) or {}
        url  = data.get("url", "").strip()
        if url and not url.startswith(("http://", "https://")):
            return jsonify({"error": "URL inválida"}), 400
        ok = ofertas.add_manual(data.get("titulo", ""), data.get("empresa", ""), url)
        return jsonify({"ok": ok})

    @app.route("/api/ofertas/preparar", methods=["POST"])
    def api_ofertas_preparar():
        data = request.get_json(force=True, silent=True) or {}
        oid  = data.get("id", "")
        run_bg(lambda: candidatura.preparar(oid), clave=f"candidatura:{oid}", que="La candidatura de esa oferta")
        return jsonify({"ok": True})

    @app.route("/api/ofertas/evaluar", methods=["POST"])
    def api_ofertas_evaluar():
        data   = request.get_json(force=True, silent=True) or {}
        modelo = data.get("modelo", ofertas.MODELO_DEFAULT)
        if data.get("id"):
            run_bg(lambda: ofertas.evaluar(data["id"], modelo), clave=f"evaluar:{data['id']}", que="La evaluación de esa oferta")
        else:
            run_bg(lambda: ofertas.evaluar_lote(modelo=modelo), clave="evaluar_lote", que="La evaluación de ofertas")
        return jsonify({"ok": True})

    @app.route("/api/ingles")
    def api_ingles():
        return jsonify(ingles.get_data())

    @app.route("/api/ingles/audio")
    def api_ingles_audio():
        try:
            ruta = ingles.audio(request.args.get("id", ""), request.args.get("que", "en"))
        except Exception as e:
            log(f"⚠ Pronunciación: {e}")
            ruta = ""
        if not ruta:
            return jsonify({"error": "sin audio"}), 404
        return send_file(ruta, mimetype="audio/wav", max_age=86400)

    @app.route("/api/ingles/repaso", methods=["POST"])
    def api_ingles_repaso():
        data = request.get_json(force=True, silent=True) or {}
        ok = ingles.repasar(data.get("id", ""), bool(data.get("acierto")))
        return jsonify({"ok": ok})

    @app.route("/api/ingles/borrar", methods=["POST"])
    def api_ingles_borrar():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": ingles.borrar(data.get("id", ""))})

    @app.route("/api/ingles/extraer", methods=["POST"])
    def api_ingles_extraer():
        run_bg(ingles.extraer, clave="ingles_extraer", que="Sacar vocabulario de las ofertas")
        return jsonify({"ok": True})

    @app.route("/api/labs")
    def api_labs():
        return jsonify(laboratorios.get_data())

    @app.route("/api/labs/vmware", methods=["POST"])
    def api_labs_vmware():
        data = request.get_json(force=True, silent=True) or {}
        vid, accion = str(data.get("id", "")), str(data.get("accion", ""))
        run_bg(lambda: laboratorios.vmware_accion(vid, accion), clave=f"vmware:{vid}", que="Esa máquina de VMware")
        return jsonify({"ok": True})

    @app.route("/api/labs/kvm", methods=["POST"])
    def api_labs_kvm():
        data = request.get_json(force=True, silent=True) or {}
        nombre, accion = str(data.get("id", "")), str(data.get("accion", ""))
        run_bg(lambda: laboratorios.kvm_accion(nombre, accion), clave=f"kvm:{nombre}", que=f"La VM {nombre}")
        return jsonify({"ok": True})

    @app.route("/api/labs/cml", methods=["POST"])
    def api_labs_cml():
        accion = str((request.get_json(force=True, silent=True) or {}).get("accion", ""))
        run_bg(lambda: laboratorios.cml_accion(accion), clave="cml", que="CML")
        return jsonify({"ok": True})

    @app.route("/api/labs/contenedores/parar", methods=["POST"])
    def api_labs_parar():
        ids = (request.get_json(force=True, silent=True) or {}).get("ids", [])
        ids = [str(i) for i in ids][:50] if isinstance(ids, list) else []
        run_bg(lambda: laboratorios.parar_contenedores(ids), clave="lab_contenedores", que="Parar contenedores")
        return jsonify({"ok": True})

    @app.route("/api/entrevistas")
    def api_entrevistas():
        return jsonify(entrevistas.listar())

    @app.route("/api/entrevistas/<sid>")
    def api_entrevista(sid):
        return jsonify(entrevistas.get(sid))

    @app.route("/api/entrevistas/nueva", methods=["POST"])
    def api_entrevista_nueva():
        data = request.get_json(force=True, silent=True) or {}
        try:
            n = int(data.get("preguntas", 6))
        except (TypeError, ValueError):
            n = 6
        sid = entrevistas.nueva(str(data.get("oferta_id", "")), str(data.get("idioma", "es")), n)
        run_bg(lambda: entrevistas.empezar(sid), clave=f"entrevista:{sid}", que="La entrevista")
        return jsonify({"id": sid})

    @app.route("/api/entrevistas/grabar", methods=["POST"])
    def api_entrevista_grabar():
        sid = str((request.get_json(force=True, silent=True) or {}).get("id", ""))
        return jsonify({"ok": entrevistas.grabar(sid)})

    @app.route("/api/entrevistas/parar", methods=["POST"])
    def api_entrevista_parar():
        sid = str((request.get_json(force=True, silent=True) or {}).get("id", ""))
        return jsonify(entrevistas.parar_y_transcribir(sid))

    @app.route("/api/entrevistas/responder", methods=["POST"])
    def api_entrevista_responder():
        data = request.get_json(force=True, silent=True) or {}
        sid, texto = str(data.get("id", "")), str(data.get("texto", ""))
        try:
            seg = int(data.get("segundos", 0))
        except (TypeError, ValueError):
            seg = 0
        audio = str(data.get("audio", ""))
        run_bg(lambda: entrevistas.responder(sid, texto, seg, audio), clave=f"entrevista:{sid}", que="La entrevista")
        return jsonify({"ok": True})

    @app.route("/api/entrevistas/terminar", methods=["POST"])
    def api_entrevista_terminar():
        sid = str((request.get_json(force=True, silent=True) or {}).get("id", ""))
        run_bg(lambda: entrevistas.informe(sid), clave=f"entrevista:{sid}", que="La entrevista")
        return jsonify({"ok": True})

    @app.route("/api/entrevistas/borrar", methods=["POST"])
    def api_entrevista_borrar():
        sid = str((request.get_json(force=True, silent=True) or {}).get("id", ""))
        return jsonify({"ok": entrevistas.borrar(sid)})

    @app.route("/api/entrevistas/audio")
    def api_entrevista_audio():
        try:
            ruta = entrevistas.audio_turno(request.args.get("id", ""), int(request.args.get("n", "-1")))
        except Exception as e:
            log(f"⚠ Voz de la entrevista: {e}")
            ruta = ""
        if not ruta:
            return jsonify({"error": "sin audio"}), 404
        return send_file(ruta, mimetype="audio/wav", max_age=3600)

    @app.route("/api/resumen")
    def api_resumen():
        return jsonify(resumen.get_data())

    @app.route("/api/resumen/generar", methods=["POST"])
    def api_resumen_generar():
        return jsonify(resumen.generar())

    @app.route("/api/tarjetas")
    def api_tarjetas():
        return jsonify(tarjetas.get_data())

    @app.route("/api/tarjetas/proponer", methods=["POST"])
    def api_tarjetas_proponer():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(tarjetas.proponer(str(data.get("imagen", "")), str(data.get("mime", "image/png")),
                                         str(data.get("texto", ""))))

    @app.route("/api/tarjetas/guardar", methods=["POST"])
    def api_tarjetas_guardar():
        data = request.get_json(force=True, silent=True) or {}
        lista = data.get("tarjetas") if isinstance(data.get("tarjetas"), list) else []
        return jsonify({"guardadas": tarjetas.guardar([t for t in lista if isinstance(t, dict)],
                                                      str(data.get("materia", "")), str(data.get("imagen", "")))})

    @app.route("/api/tarjetas/repaso", methods=["POST"])
    def api_tarjetas_repaso():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": tarjetas.repasar(str(data.get("id", "")), bool(data.get("acierto")))})

    @app.route("/api/tarjetas/borrar", methods=["POST"])
    def api_tarjetas_borrar():
        return jsonify({"ok": tarjetas.borrar(str((request.get_json(force=True, silent=True) or {}).get("id", "")))})

    @app.route("/api/tarjetas/imagen/<nombre>")
    def api_tarjetas_imagen(nombre):
        ruta = tarjetas.ruta_imagen(nombre)
        if not ruta:
            return jsonify({"error": "no existe"}), 404
        return send_file(ruta, max_age=86400)

    @app.route("/api/retos")
    def api_retos():
        return jsonify({"reto": retos.del_dia(), "resumen": retos.resumen()})

    @app.route("/api/retos/otro", methods=["POST"])
    def api_retos_otro():
        return jsonify({"reto": retos.del_dia(otro=True), "resumen": retos.resumen()})

    @app.route("/api/retos/hecho", methods=["POST"])
    def api_retos_hecho():
        return jsonify({"ok": retos.marcar_hecho(str((request.get_json(force=True, silent=True) or {}).get("id", "")))})

    @app.route("/api/retos/abrir", methods=["POST"])
    def api_retos_abrir():
        rid = str((request.get_json(force=True, silent=True) or {}).get("id", ""))
        reto = next((r for r in retos.catalogo() if r["id"] == rid), None)
        if not reto:
            return jsonify({"error": "reto desconocido"}), 404
        if reto["area"] == "linux":
            return jsonify({"ok": estudio.abrir_plataforma("certificaciones", reto["curso"])})
        if reto["area"] == "ccna":
            import subprocess
            subprocess.Popen(["xdg-open", reto["ruta"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return jsonify({"ok": True})
        return jsonify({"ok": False})

    @app.route("/api/retos/lab")
    def api_retos_lab():
        ruta = retos.ruta_de(request.args.get("id", ""))
        if not ruta.endswith(".md"):
            return jsonify({"error": "no es un lab de texto"}), 404
        with open(ruta, encoding="utf-8") as f:
            return jsonify({"md": f.read()})

    @app.route("/api/foco")
    def api_foco():
        return jsonify(foco.get_data())

    @app.route("/api/foco/empezar", methods=["POST"])
    def api_foco_empezar():
        data = request.get_json(force=True, silent=True) or {}
        try:
            minutos = int(data.get("minutos", 25))
        except (TypeError, ValueError):
            minutos = 25
        return jsonify(foco.empezar(str(data.get("materia", "")), minutos))

    @app.route("/api/foco/terminar", methods=["POST"])
    def api_foco_terminar():
        return jsonify(foco.terminar(bool((request.get_json(force=True, silent=True) or {}).get("completa"))))

    @app.route("/api/contactos")
    def api_contactos():
        return jsonify(contactos.get_data())

    @app.route("/api/contactos/guardar", methods=["POST"])
    def api_contactos_guardar():
        try:
            return jsonify({"id": contactos.guardar(request.get_json(force=True, silent=True) or {})})
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Fecha no válida ({e})"}), 400

    @app.route("/api/contactos/borrar", methods=["POST"])
    def api_contactos_borrar():
        return jsonify({"ok": contactos.borrar(str((request.get_json(force=True, silent=True) or {}).get("id", "")))})

    @app.route("/api/contactos/anotar", methods=["POST"])
    def api_contactos_anotar():
        data = request.get_json(force=True, silent=True) or {}
        try:
            dias = int(data.get("dias", 7))
        except (TypeError, ValueError):
            dias = 7
        return jsonify({"ok": contactos.anotar(str(data.get("id", "")), str(data.get("texto", "")),
                                               str(data.get("estado", "")), dias)})

    @app.route("/api/contactos/borrador", methods=["POST"])
    def api_contactos_borrador():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(contactos.borrador(str(data.get("id", "")), str(data.get("tipo", "")),
                                          str(data.get("idioma", "es")), str(data.get("oferta_id", ""))))

    @app.route("/api/agenda")
    def api_agenda():
        return jsonify(agenda.get_data())

    @app.route("/api/agenda/guardar", methods=["POST"])
    def api_agenda_guardar():
        data = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify({"id": agenda.guardar(data)})
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Fecha u hora no válida ({e})"}), 400

    @app.route("/api/agenda/borrar", methods=["POST"])
    def api_agenda_borrar():
        return jsonify({"ok": agenda.borrar(str((request.get_json(force=True, silent=True) or {}).get("id", "")))})

    @app.route("/api/agenda/hecho", methods=["POST"])
    def api_agenda_hecho():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": agenda.hecho(str(data.get("id", "")), bool(data.get("hecho")))})

    @app.route("/api/agenda.ics")
    def api_agenda_ics():
        from flask import Response
        return Response(agenda.ics(), mimetype="text/calendar",
                        headers={"Content-Disposition": "attachment; filename=agenda.ics"})

    @app.route("/api/sueldo", methods=["POST"])
    def api_sueldo():
        data = request.get_json(force=True, silent=True) or {}
        ofertas_ = data.get("ofertas") if isinstance(data.get("ofertas"), list) else []
        return jsonify({"resultados": sueldo.comparar([o for o in ofertas_ if isinstance(o, dict)])})

    @app.route("/api/redes")
    def api_redes():
        return jsonify(redes.get_data())

    @app.route("/api/redes/calcular")
    def api_redes_calcular():
        return jsonify(redes.calcular(request.args.get("cidr", "")[:60]))

    @app.route("/api/redes/diagnostico", methods=["POST"])
    def api_redes_diagnostico():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(redes.diagnostico(str(data.get("tipo", "")), str(data.get("destino", ""))))

    @app.route("/api/redes/puertos")
    def api_redes_puertos():
        return jsonify({"puertos": redes.escuchando()})

    @app.route("/api/redes/escanear", methods=["POST"])
    def api_redes_escanear():
        return jsonify(redes.escanear())

    @app.route("/api/redes/velocidad", methods=["POST"])
    def api_redes_velocidad():
        return jsonify(redes.medir_velocidad())

    @app.route("/api/redes/dispositivo", methods=["POST"])
    def api_redes_dispositivo():
        data = request.get_json(force=True, silent=True) or {}
        conocido = data.get("conocido")
        return jsonify({"ok": redes.marcar(str(data.get("clave", "")), data.get("nombre"),
                                           None if conocido is None else bool(conocido))})

    @app.route("/api/redes/subnetting", methods=["POST"])
    def api_redes_subnetting():
        data = request.get_json(force=True, silent=True) or {}
        redes.registrar_subnetting(str(data.get("tipo", "")), bool(data.get("acierto")))
        return jsonify({"ok": True})

    @app.route("/api/estudio")
    def api_estudio():
        return jsonify(estudio.get_data())

    @app.route("/api/estudio/examen", methods=["POST"])
    def api_estudio_examen():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify({"ok": estudio.set_examen(str(data.get("nombre", "")), str(data.get("fecha", "")))})

    @app.route("/api/estudio/abrir", methods=["POST"])
    def api_estudio_abrir():
        data = request.get_json(force=True, silent=True) or {}
        codigo = str(data.get("codigo", ""))
        pid = str(data.get("plataforma", "")) or ("az104" if codigo == "az104" else "certificaciones")
        return jsonify({"ok": estudio.abrir_plataforma(pid, "" if codigo == "az104" else codigo)})

    @app.route("/api/estudio/plataformas")
    def api_estudio_plataformas():
        return jsonify({"plataformas": estudio.plataformas()})

    @app.route("/api/mantenimiento")
    def api_mantenimiento():
        return jsonify(mantenimiento.get_data())

    @app.route("/api/mantenimiento/revisar", methods=["POST"])
    def api_mantenimiento_revisar():
        run_bg(mantenimiento.revisar, clave="mantenimiento", que="La revisión del sistema")
        return jsonify({"ok": True})

    @app.route("/api/mantenimiento/accion", methods=["POST"])
    def api_mantenimiento_accion():
        nombre = str((request.get_json(force=True, silent=True) or {}).get("accion", ""))
        if nombre not in mantenimiento.ACCIONES:
            return jsonify({"error": "acción desconocida"}), 400
        run_bg(lambda: mantenimiento.accion(nombre), clave=f"mant:{nombre}", que=f"El arreglo «{nombre}»")
        return jsonify({"ok": True})

    @app.route("/api/carrera")
    def api_carrera():
        return jsonify(carrera.get_data())

    @app.route("/api/carrera/tarea", methods=["POST"])
    def api_carrera_tarea():
        data = request.get_json(force=True, silent=True) or {}
        ok = carrera.toggle_tarea(data.get("id", ""))
        return jsonify({"ok": ok})

    @app.route("/api/carrera/tarea/nueva", methods=["POST"])
    def api_carrera_tarea_nueva():
        data = request.get_json(force=True, silent=True) or {}
        ok = carrera.add_tarea(data.get("objetivo_id", ""), data.get("texto", ""))
        return jsonify({"ok": ok})

    @app.route("/api/carrera/tarea/borrar", methods=["POST"])
    def api_carrera_tarea_borrar():
        data = request.get_json(force=True, silent=True) or {}
        ok = carrera.del_tarea(data.get("id", ""))
        return jsonify({"ok": ok})

    @app.route("/api/carrera/logro", methods=["POST"])
    def api_carrera_logro():
        data = request.get_json(force=True, silent=True) or {}
        ok = carrera.add_logro(data.get("texto", ""))
        return jsonify({"ok": ok})

    @app.route("/api/carrera/logro/borrar", methods=["POST"])
    def api_carrera_logro_borrar():
        data = request.get_json(force=True, silent=True) or {}
        ok = carrera.del_logro(data.get("id", ""))
        return jsonify({"ok": ok})

    @app.route("/api/carrera/coach", methods=["POST"])
    def api_carrera_coach():
        data = request.get_json(force=True, silent=True) or {}
        modelo = data.get("modelo", carrera.MODELO_COACH_DEFAULT)
        run_bg(lambda: carrera.coach(modelo), clave="coach", que="El coach de carrera")
        return jsonify({"ok": True})

    @app.route("/api/carrera/cv/estado")
    def api_carrera_cv_estado():
        import carrera_cv
        return jsonify(carrera_cv.estado())

    @app.route("/api/carrera/cv/proponer", methods=["POST"])
    def api_carrera_cv_proponer():
        import carrera_cv
        data = request.get_json(force=True, silent=True) or {}
        texto = (data.get("texto") or "").strip()
        if not texto:
            return jsonify({"error": "Falta el texto del logro"}), 400
        modelo = data.get("modelo", carrera_cv.MODELO_DEFAULT)
        run_bg(lambda: carrera_cv.proponer(texto, modelo), clave="cv_proponer", que="La propuesta para el CV")
        return jsonify({"ok": True})

    @app.route("/api/carrera/cv/aplicar", methods=["POST"])
    def api_carrera_cv_aplicar():
        import carrera_cv
        data = request.get_json(force=True, silent=True) or {}
        try:
            res = carrera_cv.aplicar(data.get("seccion", ""), data.get("item"))
            return jsonify(res)
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/quit", methods=["POST"])
    def api_quit():
        def worker():
            log("🛑 Apagando sistema...")
            time.sleep(0.5)
            os._exit(0)
        run_bg(worker, cupo=False)
        return jsonify({"ok": True})

    @app.route("/api/open/<service_id>", methods=["POST"])
    def api_open(service_id):
        svc = SERVICES.get(service_id)
        if svc and svc.get("url"):
            try:
                webbrowser.open(svc["url"])
                log(f"↗ Abriendo {svc['label']} en el navegador del servidor")
                return jsonify({"ok": True})
            except Exception as e:
                log(f"❌ Error al abrir el navegador: {e}")
                return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Acción no soportada"}), 400

    @app.route("/api/logs")
    def api_logs():
        return jsonify(list(_log_buffer))

    @app.route("/api/start-all", methods=["POST"])
    def api_start_all():
        def worker():
            log("🚀 Iniciando TODOS los servicios (escalonado)...")
            for sid in SERVICES:
                run_bg(lambda s=sid: _toggle(s, "start"), clave=f"servicio:{sid}", que=SERVICES[sid]["label"])
                time.sleep(1.2)
        run_bg(worker, clave="todos", que="Iniciar todo")
        return jsonify({"ok": True})

    @app.route("/api/stop-all", methods=["POST"])
    def api_stop_all():
        def worker():
            log("⛔ Deteniendo TODOS los servicios...")
            for sid in SERVICES:
                run_bg(lambda s=sid: _toggle(s, "stop"), clave=f"servicio:{sid}", que=SERVICES[sid]["label"])
                time.sleep(0.8)
        run_bg(worker, clave="todos", que="Detener todo")
        return jsonify({"ok": True})

    @app.route("/api/scan", methods=["POST"])
    def api_scan():
        log("🔍 Escaneando estado de todos los servicios...")
        running = get_all_statuses()
        log("✓ Radar completado — panel sincronizado")
        return jsonify({
            "services": running,
            "system":   get_system_stats(),
            "health":   get_health_statuses(running),
            "uptimes":  get_uptimes(running),
        })

    @socketio.on("connect")
    def on_connect():
        log("✓ Panel conectado")

    return app
