import os
import glob
import subprocess
import time

from extensions import socketio
from services import SERVICES, RUTA_UPDATE_ACE, RUTA_METUBE_DIR, RUTA_OBSIDIAN
from status import log, invalidate_status_cache

# ─── Ejecutar comandos sin dar por bueno lo que falló ──────────────────────────
class FalloComando(Exception):
    pass

def _cmd(args: list, que: str, **kwargs):
    """Ejecuta args; si termina con error, lanza FalloComando diciendo qué paso falló y por qué."""
    r = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout or "").strip().splitlines()
        raise FalloComando(f"{que} (código {r.returncode})" + (f": {detalle[-1][:200]}" if detalle else ""))
    return r

def _quitar(*contenedores):
    """Para y borra contenedores; si no existían, no pasa nada."""
    for c in contenedores:
        subprocess.run(["podman", "stop", c], capture_output=True)
        subprocess.run(["podman", "rm",   c], capture_output=True)

def _bajar(*imagenes):
    """Descarga las imágenes ANTES de tocar nada: si falla (sin red, registro caído…),
    el servicio sigue funcionando con la versión que tenía."""
    for img in imagenes:
        _cmd(["podman", "pull", img], f"descargar {img.split('/')[-1]}")

# ─── Motor de acciones ─────────────────────────────────────────────────────────
def _ejecutar_accion(service_id: str, action: str, act: dict):
    label = SERVICES[service_id]["label"]
    atype = act["type"]

    try:
        if atype == "podman":
            for c in act["containers"]:
                r = subprocess.run(["podman", action, c], capture_output=True)
                if r.returncode != 0:
                    log(f"❌ {label}: error al {'iniciar' if action == 'start' else 'detener'}")
                    return
            log(f"{label} {'iniciado' if action == 'start' else 'detenido'}")

        elif atype == "group":
            fallidos = [c for c in act["containers"]
                        if subprocess.run(["podman", action, c], capture_output=True).returncode != 0]
            if fallidos:
                log(f"❌ {label}: no pude {'iniciar' if action == 'start' else 'detener'} {', '.join(fallidos)}")
                return
            log(f"{label} {'iniciado' if action == 'start' else 'detenido'}")

        elif atype == "first":
            cname  = act["container"]
            exists = subprocess.run(["podman", "container", "exists", cname]).returncode == 0
            if not exists:
                log(f"🆕 Primera vez — descargando {act['image'].split('/')[-1]}...")
                cmd = ["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", cname]
                for p in act.get("ports", []):
                    cmd += ["-p", p]
                for v in act.get("volumes", []):
                    cmd += ["-v", v]
                cmd += [act["image"]]
                _cmd(cmd, f"crear el contenedor {cname}")
            else:
                _cmd(["podman", "start", cname], f"arrancar {cname}")
            log(f"✓ {label} iniciado")

        elif atype == "first_scrutiny":
            cname  = "scrutiny"
            exists = subprocess.run(["podman", "container", "exists", cname]).returncode == 0
            if not exists:
                log("🆕 Primera vez — descargando Scrutiny...")
                devices     = glob.glob("/dev/sd?") + glob.glob("/dev/nvme?n?")
                device_args = []
                for dev in devices:
                    device_args += ["--device", f"{dev}:{dev}"]
                _cmd([
                    "podman", "run", "-d", "--label", "io.containers.autoupdate=registry",
                    "--name", "scrutiny", "-p", "8099:8080",
                    "--cap-add", "SYS_RAWIO",
                    "-v", "/run/udev:/run/udev:ro",
                    "-v", "scrutiny_config:/opt/scrutiny/config",
                    "-v", "scrutiny_influxdb:/opt/scrutiny/influxdb",
                ] + device_args + ["ghcr.io/analogj/scrutiny:master-omnibus"], "crear el contenedor scrutiny")
            else:
                _cmd(["podman", "start", "scrutiny"], "arrancar scrutiny")
            log("✓ Scrutiny iniciado")

        elif atype == "script":
            # start y stop comparten esta rama: el mensaje tiene que seguir a
            # `action`, o el log dice "iniciado" mientras corre el script de apagado.
            verbo, hecho = ("Iniciando", "iniciado") if action == "start" else ("Deteniendo", "detenido")
            socketio.emit("progress", {"id": service_id, "active": True})
            log(f"{verbo} {label}...")
            try:
                kwargs = {}
                if act.get("timeout"):
                    kwargs["timeout"] = act["timeout"]
                r = subprocess.run(["bash", act["path"]], **kwargs)
                if r.returncode != 0:
                    log(f"❌ {label}: el script {os.path.basename(act['path'])} terminó con error (código {r.returncode})")
                    return
                log(f"✓ {label} {hecho}")
            finally:
                socketio.emit("progress", {"id": service_id, "active": False})

        elif atype == "process":
            subprocess.Popen([act["binary"]] + act.get("args", []))
            log(f"{label} iniciado")

        elif atype == "process_safe":
            pattern = act.get("guard", act["binary"].split("/")[-1])
            already = subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0
            if already:
                log(f"⚠ {label} ya está corriendo — no se abre una segunda instancia")
            else:
                subprocess.Popen([act["binary"]] + act.get("args", []))
                log(f"{label} iniciado")

        elif atype == "ace":
            exists = subprocess.run(["podman", "container", "exists", "ace-audio"]).returncode == 0
            if not exists:
                log("🆕 El contenedor no existe. Iniciando instalación automatizada...")
                r = subprocess.run(["bash", RUTA_UPDATE_ACE])
                if r.returncode != 0:
                    log("❌ Error al construir el contenedor de ACE-Step")
                    return
            else:
                r = subprocess.run(["podman", "start", "ace-audio"], capture_output=True)
                if r.returncode != 0:
                    log("❌ ACE-Step: error al iniciar el contenedor")
                    return
            log("🎵 Estudio Musical IA iniciado")

        elif atype == "pkill":
            subprocess.run(["pkill", "-9", "-f", act["pattern"]])
            if act.get("port"):
                subprocess.run(["fuser", "-k", f"{act['port']}/tcp"], capture_output=True)
            log(f"{label} detenido")

        elif atype == "rm":
            _cmd(["podman", "rm", "-f"] + act["containers"], "borrar los contenedores")
            log(f"{label} detenido y purgado")

    except FalloComando as e:
        log(f"❌ {label}: no se pudo {e}")
    except Exception as e:
        log(f"❌ Error en la acción '{action}' para {service_id}: {str(e)}")

def _toggle(service_id: str, action: str):
    act = SERVICES[service_id].get("actions", {}).get(action)
    if act is None:
        log(f"❌ Acción '{action}' no definida para {service_id}")
        return
    _ejecutar_accion(service_id, action, act)
    invalidate_status_cache()

# ─── Handlers de actualización ─────────────────────────────────────────────────
UPDATE_HANDLERS = {}

def _upd(name):
    def wrapper(fn):
        UPDATE_HANDLERS[name] = fn
        return fn
    return wrapper

@_upd("portainer")
def _update_portainer():
    _bajar("docker.io/portainer/portainer-ce:latest")
    _quitar("portainer")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry",
          "-p", "8000:8000", "-p", "9443:9443", "-p", "9000:9000",
          "--name", "portainer",
          "-v", "portainer_data:/data",
          "-v", f"/run/user/{os.getuid()}/podman/podman.sock:/var/run/docker.sock",
          "docker.io/portainer/portainer-ce:latest"], "crear el contenedor portainer")

@_upd("paperless")
def _update_paperless():
    _bajar("docker.io/library/redis:7-alpine", "docker.io/paperlessngx/paperless-ngx:latest")
    _quitar("paperless", "paperless-redis")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "paperless-redis",
          "--network", "paperless-net", "docker.io/library/redis:7-alpine"], "crear el contenedor paperless-redis")
    ruta_data    = os.path.expanduser("~/paperless/data") + ":/usr/src/paperless/data"
    ruta_media   = os.path.expanduser(os.environ.get("PAPERLESS_MEDIA", "~/paperless/media")) + ":/usr/src/paperless/media"
    ruta_consume = os.path.expanduser(os.environ.get("PAPERLESS_CONSUME", "~/paperless/consume")) + ":/usr/src/paperless/consume"
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "paperless",
          "--network", "paperless-net",
          "-e", "PAPERLESS_REDIS=redis://paperless-redis:6379",
          "-v", ruta_data, "-v", ruta_media, "-v", ruta_consume,
          "-p", "8010:8000", "docker.io/paperlessngx/paperless-ngx:latest"], "crear el contenedor paperless")

@_upd("paperless-ai")
def _update_paperless_ai():
    _bajar("docker.io/clusterzx/paperless-ai:latest")
    _quitar("paperless-ai")
    carpeta = os.path.expanduser("~/paperless-ai-data")
    os.makedirs(carpeta, exist_ok=True)
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "paperless-ai",
          "--network", "paperless-net",
          "-p", "3030:3000",
          "--add-host", "host.containers.internal:host-gateway",
          "-v", carpeta + ":/app/data",
          "docker.io/clusterzx/paperless-ai:latest"], "crear el contenedor paperless-ai")

@_upd("immich")
def _update_immich():
    # immich-server también se baja: antes no estaba en la lista y «podman run» reutilizaba
    # la imagen vieja, así que el servidor nunca se actualizaba.
    _bajar("docker.io/tensorchord/pgvecto-rs:pg14-v0.2.0", "docker.io/library/redis:6.2-alpine",
           "ghcr.io/immich-app/immich-machine-learning:release", "ghcr.io/immich-app/immich-server:release")
    _quitar("immich_server", "immich_machine_learning", "immich_redis", "immich_postgres")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "immich_postgres",
          "--network", "immich-net",
          "-e", "POSTGRES_PASSWORD=postgres", "-e", "POSTGRES_USER=postgres", "-e", "POSTGRES_DB=immich",
          "-v", "immich_db:/var/lib/postgresql/data",
          "docker.io/tensorchord/pgvecto-rs:pg14-v0.2.0"], "crear el contenedor immich_postgres")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "immich_redis",
          "--network", "immich-net", "docker.io/library/redis:6.2-alpine"], "crear el contenedor immich_redis")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "immich_machine_learning",
          "--network", "immich-net",
          "--device", "nvidia.com/gpu=all",
          "-v", "immich_model_cache:/cache",
          "ghcr.io/immich-app/immich-machine-learning:release"], "crear el contenedor immich_machine_learning")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "immich_server",
          "--network", "immich-net", "-p", "2283:2283",
          "-e", "DB_HOSTNAME=immich_postgres", "-e", "DB_USERNAME=postgres",
          "-e", "DB_PASSWORD=postgres",       "-e", "DB_DATABASE_NAME=immich",
          "-e", "REDIS_HOSTNAME=immich_redis",
          "-v", os.path.expanduser("~/immich-app/upload") + ":/usr/src/app/upload",
          "-v", "/etc/localtime:/etc/localtime:ro",
          "ghcr.io/immich-app/immich-server:release"], "crear el contenedor immich_server")

@_upd("bentopdf")
def _update_bentopdf():
    _bajar("ghcr.io/alam00000/bentopdf:latest")
    _quitar("bentopdf")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "bentopdf",
          "-p", "8081:8080", "ghcr.io/alam00000/bentopdf:latest"], "crear el contenedor bentopdf")

@_upd("ace-audio")
def _update_ace():
    log("⏳ Reconstruyendo imagen Podman de ACE-Step (puede tardar 5-10 min)...")
    _cmd(["bash", RUTA_UPDATE_ACE], "reconstruir la imagen de ACE-Step")

def _version_ytdlp():
    venv_py = os.path.join(RUTA_METUBE_DIR, "venv", "bin", "python")
    r = subprocess.run([venv_py, "-c", "import yt_dlp;print(yt_dlp.version.__version__)"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "?"


@_upd("metube")
def _update_metube():
    log("⏳ Actualizando MeTube (git pull + dependencias)...")
    _cmd(["git", "-C", RUTA_METUBE_DIR, "pull"], "traer los cambios de MeTube (git pull)")

    venv_pip = os.path.join(RUTA_METUBE_DIR, "venv", "bin", "pip")
    antes = _version_ytdlp()

    # -U es imprescindible: sin él, "pip install yt-dlp" sobre un paquete ya
    # instalado responde "Requirement already satisfied" y no actualiza nada. Este
    # handler llevaba yt-dlp en la lista desde el principio y jamás lo subió de
    # versión — de ahí los HTTP 403 de YouTube, que aparecen cuando yt-dlp se
    # queda atrás del reproductor.
    _cmd([venv_pip, "install", "-q", "-U", "aiohttp", "python-socketio", "yt-dlp", "watchfiles"],
         "actualizar las dependencias de MeTube (pip)")

    despues = _version_ytdlp()
    if antes == despues:
        log(f"✓ yt-dlp ya estaba al día ({despues})")
    else:
        log(f"⬆ yt-dlp {antes} → {despues}")

    # Reinicio automático: MeTube importa yt-dlp al arrancar, así que sin esto la
    # versión nueva queda en disco pero el proceso sigue con la vieja en memoria.
    # .get(), no "in": get_all_statuses devuelve {id: bool} con TODOS los
    # servicios, así que la clave existe siempre y "in" daría verdadero incluso
    # con MeTube apagado — lo encendería sin que nadie lo pida.
    from status import get_all_statuses
    if get_all_statuses().get("metube"):
        log("↺ Reiniciando MeTube para cargar la versión nueva...")
        _restart("metube")
    else:
        log("✓ MeTube actualizado (está apagado; se aplicará al encenderlo)")

@_upd("uptime-kuma")
def _update_uptime_kuma():
    _bajar("docker.io/louislam/uptime-kuma:latest")
    _quitar("uptime-kuma")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "uptime-kuma",
          "-p", "3001:3001", "-v", "uptime-kuma_data:/app/data",
          "docker.io/louislam/uptime-kuma:latest"], "crear el contenedor uptime-kuma")

@_upd("vaultwarden")
def _update_vaultwarden():
    _bajar("docker.io/vaultwarden/server:latest")
    _quitar("vaultwarden")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "vaultwarden",
          "-p", "8585:80", "-v", "vaultwarden_data:/data",
          "docker.io/vaultwarden/server:latest"], "crear el contenedor vaultwarden")

@_upd("scrutiny")
def _update_scrutiny():
    _bajar("ghcr.io/analogj/scrutiny:master-omnibus")
    _quitar("scrutiny")
    devices     = glob.glob("/dev/sd?") + glob.glob("/dev/nvme?n?")
    device_args = []
    for dev in devices:
        device_args += ["--device", f"{dev}:{dev}"]
    _cmd([
        "podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "scrutiny",
        "-p", "8099:8080", "--cap-add", "SYS_RAWIO",
        "-v", "/run/udev:/run/udev:ro",
        "-v", "scrutiny_config:/opt/scrutiny/config",
        "-v", "scrutiny_influxdb:/opt/scrutiny/influxdb",
    ] + device_args + ["ghcr.io/analogj/scrutiny:master-omnibus"], "crear el contenedor scrutiny")

@_upd("obsidian")
def _update_obsidian():
    import urllib.request, json
    log("⏳ Buscando última versión de Obsidian...")
    try:
        with urllib.request.urlopen("https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest", timeout=10) as r:
            release = json.loads(r.read())
        version = release["tag_name"]
        url     = next(a["browser_download_url"] for a in release["assets"] if a["name"].endswith(".AppImage") and "arm" not in a["name"])
    except Exception as e:
        raise FalloComando(f"consultar la última versión en GitHub: {e}")
    log(f"⬇ Descargando Obsidian {version}...")
    try:
        tmp = RUTA_OBSIDIAN + ".tmp"
        urllib.request.urlretrieve(url, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, RUTA_OBSIDIAN)
    except Exception as e:
        raise FalloComando(f"descargar Obsidian {version}: {e}")
    log(f"Obsidian {version} descargado — reinicia Obsidian para aplicarlo")

@_upd("it-tools")
def _update_it_tools():
    _bajar("docker.io/corentinth/it-tools:latest")
    _quitar("it-tools")
    _cmd(["podman", "run", "-d", "--label", "io.containers.autoupdate=registry", "--name", "it-tools",
          "-p", "8084:80", "docker.io/corentinth/it-tools:latest"], "crear el contenedor it-tools")

@_upd("omniroute")
def _update_omniroute():
    IMAGE = "docker.io/diegosouzapw/omniroute:latest"
    _bajar(IMAGE)
    _quitar("omniroute")
    _cmd(["podman", "run", "-d",
          "--name", "omniroute",
          "--stop-timeout", "40",
          "-p", "127.0.0.1:20128:20128",
          "-v", "omniroute-data:/app/data",
          IMAGE], "crear el contenedor omniroute")

# ─── Restart ──────────────────────────────────────────────────────────────────
def _restart(service_id: str):
    log(f"↺ Reiniciando {SERVICES[service_id]['label']}...")
    _toggle(service_id, "stop")
    time.sleep(2)
    _toggle(service_id, "start")

# ─── Dispatcher de updates ─────────────────────────────────────────────────────
def _do_update(service_id: str):
    socketio.emit("progress", {"id": service_id, "active": True})
    log(f"🔄 Actualizando {SERVICES[service_id]['label']}...")
    try:
        handler = UPDATE_HANDLERS.get(service_id)
        if not handler:
            log(f"⚠️ No hay actualización definida para {service_id}")
            return
        handler()   # si algo falla, lanza: el «✓» solo sale si todo fue bien
        log(f"✓ {SERVICES[service_id]['label']} actualizado correctamente")
    except FalloComando as e:
        log(f"❌ {SERVICES[service_id]['label']}: la actualización se paró al {e}")
    except Exception as e:
        log(f"❌ Error en actualización de {service_id}: {e}")
    finally:
        socketio.emit("progress", {"id": service_id, "active": False})
