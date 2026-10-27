import os
import ssl
import subprocess
import threading
import datetime
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil

from extensions import socketio
from services import SERVICES

# ─── Log persistente ───────────────────────────────────────────────────────────
LOG_FILE        = os.path.expanduser(os.environ.get("LOG_FILE", "~/MiPanelControl/panel.log"))
LOG_MAX_SIZE    = 512 * 1024
LOG_BACKUP_COUNT = 3
_log_buffer     = deque(maxlen=300)

def _rotar_log():
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_SIZE:
        for i in range(LOG_BACKUP_COUNT - 1, 0, -1):
            bak  = f"{LOG_FILE}.{i}"
            prev = f"{LOG_FILE}.{i - 1}" if i > 1 else LOG_FILE
            if os.path.exists(bak):
                os.remove(bak)
            if os.path.exists(prev):
                os.rename(prev, bak)

def log(msg: str):
    ts   = datetime.datetime.now().strftime("%H:%M:%S")
    full = f"[{ts}] {msg}"
    _log_buffer.append(full)
    try:
        _rotar_log()
        with open(LOG_FILE, "a") as f:
            f.write(full + "\n")
    except Exception:
        pass
    try:
        socketio.emit("log", {"ts": ts, "msg": msg})
    except Exception:
        pass

# ─── Tareas en segundo plano ──────────────────────────────────────────────────
# Antes cada petición abría su hilo y nada impedía lanzar dos veces lo mismo (dos
# actualizaciones del mismo servicio, dos conversiones, dos llamadas al modelo…).
# Ahora: como mucho MAX_TAREAS a la vez (las demás esperan turno y lo dicen en el
# log) y, si una tarea tiene `clave`, no se lanza otra con la misma clave mientras
# la primera siga en marcha.
MAX_TAREAS   = int(os.environ.get("MAX_TAREAS", "4"))
_cupo        = threading.BoundedSemaphore(MAX_TAREAS)
_en_marcha   = {}            # clave -> qué es (para el aviso)
_marcha_lock = threading.Lock()

def run_bg(fn, clave: str = None, que: str = None, cupo: bool = True) -> bool:
    """Lanza fn en segundo plano. Devuelve False si ya había una tarea con esa clave.
    cupo=False solo para lo que no puede esperar turno (apagar el panel)."""
    if clave:
        with _marcha_lock:
            if clave in _en_marcha:
                log(f"⏳ {_en_marcha[clave]} ya está en marcha: espera a que termine")
                return False
            _en_marcha[clave] = que or clave

    def tarea():
        try:
            if cupo:
                if not _cupo.acquire(blocking=False):
                    log(f"⏳ Hay {MAX_TAREAS} tareas en marcha; «{que or clave or 'esta tarea'}» empieza en cuanto termine una")
                    _cupo.acquire()
            try:
                fn()
            finally:
                if cupo:
                    _cupo.release()
        except Exception as e:
            log(f"❌ {que or 'Tarea en segundo plano'}: {e}")
        finally:
            if clave:
                with _marcha_lock:
                    _en_marcha.pop(clave, None)

    threading.Thread(target=tarea, daemon=True).start()
    return True

def tareas_en_marcha() -> list:
    with _marcha_lock:
        return sorted(_en_marcha.values())

# ─── Caché de estado ───────────────────────────────────────────────────────────
_status_cache  = {"containers": None, "ts": 0, "processes": {}}
STATUS_CACHE_TTL = 5

def invalidate_status_cache():
    _status_cache["containers"] = None
    _status_cache["ts"]         = 0
    _status_cache["processes"]  = {}

# ─── Detección de estado ───────────────────────────────────────────────────────
def get_running_containers():
    now = time.time()
    if _status_cache["containers"] is not None and (now - _status_cache["ts"]) < STATUS_CACHE_TTL:
        return _status_cache["containers"]
    try:
        result = subprocess.run(
            ["podman", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True,
        )
        _status_cache["containers"] = result.stdout.split()
        _status_cache["ts"]         = now
        return _status_cache["containers"]
    except Exception:
        return []

def is_process_running(pattern: str) -> bool:
    now    = time.time()
    cached = _status_cache["processes"].get(pattern)
    if cached is not None and (now - _status_cache["ts"]) < STATUS_CACHE_TTL:
        return cached
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0
        _status_cache["processes"][pattern] = result
        return result
    except Exception:
        return False

def is_module_loaded(name: str) -> bool:
    try:
        with open("/proc/modules", encoding="utf-8") as fh:
            return any(line.startswith(name + " ") for line in fh)
    except Exception:
        return False

def get_all_statuses() -> dict:
    running = get_running_containers()
    status  = {}
    for sid, svc in SERVICES.items():
        if svc.get("containers"):
            status[sid] = any(c in running for c in svc["containers"])
        elif svc.get("process"):
            status[sid] = is_process_running(svc["process"])
        elif svc.get("kmod"):
            # Que el módulo esté cargado no basta: si el rival sigue dentro es él
            # quien tiene tomado el hardware (VT-x, el transporte vsock) y el
            # servicio no arrancará. vboxdrv, p.ej., lo carga vboxdrv.service al
            # boot y estaría siempre en verde aunque KVM tenga VT-x.
            conflict    = svc.get("kmod_conflict")
            status[sid] = (
                is_module_loaded(svc["kmod"])
                and not (conflict and is_module_loaded(conflict))
            )
        else:
            status[sid] = False
    return status

def _get_gpu_stats():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        util, mem_used, mem_total, temp = [x.strip() for x in out.stdout.strip().split(",")]
        return {
            "util": round(float(util), 1),
            "mem_used": int(float(mem_used)),
            "mem_total": int(float(mem_total)),
            "temp": round(float(temp), 1),
        }
    except Exception:
        return None

def get_system_stats() -> dict:
    try:
        return {
            "cpu":  round(psutil.cpu_percent(interval=0.1), 1),
            "ram":  round(psutil.virtual_memory().percent,  1),
            "disk": round(psutil.disk_usage("/").percent,    1),
            "gpu":  _get_gpu_stats(),
        }
    except Exception:
        return {"cpu": 0, "ram": 0, "disk": 0, "gpu": None}

# ─── Healthchecks ──────────────────────────────────────────────────────────────
_health_cache      = {}
_health_cache_lock = threading.Lock()
HEALTH_CACHE_TTL   = 12

def _check_one_health(service_id: str, url: str, timeout: int = 3) -> tuple:
    now = time.time()
    with _health_cache_lock:
        cached = _health_cache.get(service_id)
        if cached and (now - cached["ts"]) < HEALTH_CACHE_TTL:
            return service_id, cached["status"]
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout, context=ctx)
        status = "healthy"
    except Exception:
        status = "unhealthy"
    with _health_cache_lock:
        _health_cache[service_id] = {"status": status, "ts": time.time()}
    return service_id, status

def get_health_statuses(running: dict) -> dict:
    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(_check_one_health, sid, svc["url"])
            for sid, svc in SERVICES.items()
            if running.get(sid) and svc.get("url")
        ]
        for f in as_completed(futures):
            sid, status       = f.result()
            results[sid]      = status
    return results

# ─── Uptime ────────────────────────────────────────────────────────────────────
def get_uptimes(statuses: dict) -> dict:
    uptimes = {}
    for sid, is_running in statuses.items():
        if not is_running:
            uptimes[sid] = None
            continue
        svc = SERVICES[sid]
        try:
            if svc.get("process"):
                r    = subprocess.run(["pgrep", "-f", svc["process"]], capture_output=True, text=True)
                pids = [p for p in r.stdout.strip().split() if p.isdigit()]
                if pids:
                    uptimes[sid] = int(time.time() - psutil.Process(int(pids[0])).create_time())
                else:
                    uptimes[sid] = None
            elif svc.get("containers"):
                r = subprocess.run(
                    ["podman", "inspect", svc["containers"][0], "--format", "{{.State.StartedAt}}"],
                    capture_output=True, text=True,
                )
                if r.returncode == 0 and r.stdout.strip():
                    ts = r.stdout.strip()
                    if '.' in ts:
                        base, frac = ts.split('.', 1)
                        ts = f"{base}.{frac.rstrip('Z')[:6]}+00:00"
                    else:
                        ts = ts.replace('Z', '+00:00')
                    from datetime import timezone as _tz
                    dt = datetime.datetime.fromisoformat(ts)
                    uptimes[sid] = int(time.time() - dt.timestamp())
                else:
                    uptimes[sid] = None
            else:
                uptimes[sid] = None
        except Exception:
            uptimes[sid] = None
    return uptimes

# ─── Monitor de notificaciones ─────────────────────────────────────────────────
_prev_health: dict = {}

def _notification_loop():
    time.sleep(20)  # esperar a que los servicios arranquen
    while True:
        try:
            statuses = get_all_statuses()
            health   = get_health_statuses(statuses)
            for sid, status in health.items():
                prev = _prev_health.get(sid)
                if prev == "healthy" and status == "unhealthy":
                    label = SERVICES[sid]["label"]
                    log(f"⚠ {label} no responde — enviando notificación")
                    try:
                        from plyer import notification as _n
                        _n.notify(title=f"⚠ {label} caído",
                                  message=f"{label} no responde en {SERVICES[sid].get('url','')}",
                                  timeout=8)
                    except Exception:
                        pass
                _prev_health[sid] = status
        except Exception:
            pass
        time.sleep(30)

def start_notification_monitor():
    threading.Thread(target=_notification_loop, daemon=True).start()
