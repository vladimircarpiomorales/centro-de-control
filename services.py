import os
from dotenv import load_dotenv

load_dotenv()

# ─── Rutas configurables ───────────────────────────────────────────────────────
RUTA_PDF_EJECUTABLE = os.path.expanduser(os.environ.get("RUTA_PDF_EJECUTABLE", "~/venv/bin/opendataloader-pdf-hybrid"))
RUTA_IA_SCRIPT      = os.path.expanduser(os.environ.get("RUTA_IA_SCRIPT",      "~/MiPanelControl/ia-up.sh"))
RUTA_OLLAMA_SCRIPT  = os.path.expanduser(os.environ.get("RUTA_OLLAMA_SCRIPT",  "~/MiPanelControl/ollama-up.sh"))
RUTA_PYVIDEO_SCRIPT = os.path.expanduser(os.environ.get("RUTA_PYVIDEO_SCRIPT", "~/MiPanelControl/pyvideotrans.sh"))
RUTA_ACE_SCRIPT     = os.path.expanduser(os.environ.get("RUTA_ACE_SCRIPT",     "~/MiPanelControl/ace-up.sh"))
RUTA_RESUME_SCRIPT  = os.path.expanduser(os.environ.get("RUTA_RESUME_SCRIPT",  "~/MiPanelControl/resume-up.sh"))
RUTA_UPDATE_ACE     = os.path.expanduser(os.environ.get("RUTA_UPDATE_ACE",     "~/MiPanelControl/update_ace.sh"))
RUTA_METUBE_SCRIPT  = os.path.expanduser(os.environ.get("RUTA_METUBE_SCRIPT",  "~/MiPanelControl/metube-up.sh"))
RUTA_METUBE_DIR     = os.path.expanduser(os.environ.get("RUTA_METUBE_DIR",     "~/MiPanelControl/metube"))
RUTA_VBOX_ON        = os.path.expanduser(os.environ.get("RUTA_VBOX_ON",        "~/MiPanelControl/vbox-on.sh"))
RUTA_VBOX_OFF       = os.path.expanduser(os.environ.get("RUTA_VBOX_OFF",       "~/MiPanelControl/vbox-off.sh"))
RUTA_COWORK_ON      = os.path.expanduser(os.environ.get("RUTA_COWORK_ON",      "~/MiPanelControl/cowork-on.sh"))
RUTA_COWORK_OFF     = os.path.expanduser(os.environ.get("RUTA_COWORK_OFF",     "~/MiPanelControl/cowork-off.sh"))
RUTA_OBSIDIAN       = os.path.expanduser(os.environ.get("RUTA_OBSIDIAN",       "~/Downloads/Obsidian.AppImage"))
RUTA_OBSIDIAN_VAULT    = os.path.expanduser(os.environ.get("RUTA_OBSIDIAN_VAULT",    "~/Obsidian"))
RUTA_OMNIROUTE_SCRIPT  = os.path.expanduser(os.environ.get("RUTA_OMNIROUTE_SCRIPT",  "~/MiPanelControl/omniroute-up.sh"))
# Los manuales convertidos (PDF/EPUB → Markdown) caen dentro del vault de Obsidian
# ("Personal" es la carpeta real del vault — donde vive el .obsidian/ de config)
# para aprovechar su buscador/grafo en vez de mantener uno propio.
RUTA_MANUALES_MD    = os.path.expanduser(os.environ.get("RUTA_MANUALES_MD",    os.path.join(RUTA_OBSIDIAN_VAULT, "Personal", "Manuales")))

# ─── Catálogo de servicios ─────────────────────────────────────────────────────
# Campos por servicio:
#   containers:  lista de nombres podman para detectar estado
#   process:     patrón pgrep para servicios sin contenedor
#   actions:     define start/stop por tipo
#                tipos: podman, group, first, first_scrutiny, script, process, pkill, rm, ace

SERVICES = {
    "portainer": {
        "label": "Portainer",
        "tab": "podman",
        "port": 9443,
        "url": "https://127.0.0.1:9443",
        "image": "docker.io/portainer/portainer-ce:latest",
        "meta": "Gestión de contenedores",
        "has_update": True,
        "containers": ["portainer"],
        "actions": {
            "start": {"type": "podman", "containers": ["portainer"]},
            "stop":  {"type": "podman", "containers": ["portainer"]},
        },
    },
    "paperless": {
        "label": "Paperless-ngx",
        "tab": "podman",
        "port": 8010,
        "url": "http://127.0.0.1:8010",
        "image": "docker.io/paperlessngx/paperless-ngx:latest",
        "meta": "Gestión documental",
        "has_update": True,
        "containers": ["paperless-redis", "paperless"],
        "actions": {
            "start": {"type": "group", "containers": ["paperless-redis", "paperless"]},
            "stop":  {"type": "group", "containers": ["paperless", "paperless-redis"]},
        },
    },
    "paperless-ai": {
        "label": "Paperless-AI",
        "tab": "podman",
        "port": 3030,
        "url": "http://127.0.0.1:3030",
        "image": "docker.io/clusterzx/paperless-ai:latest",
        "meta": "IA documental",
        "has_update": True,
        "containers": ["paperless-ai"],
        "actions": {
            "start": {"type": "podman", "containers": ["paperless-ai"]},
            "stop":  {"type": "podman", "containers": ["paperless-ai"]},
        },
    },
    "immich": {
        "label": "Immich Photos",
        "tab": "podman",
        "port": 2283,
        "url": "http://127.0.0.1:2283",
        "image": "ghcr.io/immich-app/immich-server:release",
        "meta": "Galería · 4 contenedores",
        "has_update": True,
        "containers": ["immich_postgres", "immich_redis", "immich_machine_learning", "immich_server"],
        "actions": {
            "start": {"type": "group", "containers": ["immich_postgres", "immich_redis", "immich_machine_learning", "immich_server"]},
            "stop":  {"type": "group", "containers": ["immich_server", "immich_machine_learning", "immich_redis", "immich_postgres"]},
        },
    },
    "bentopdf": {
        "label": "BentoPDF",
        "tab": "podman",
        "port": 8081,
        "url": "http://127.0.0.1:8081",
        "image": "ghcr.io/alam00000/bentopdf:latest",
        "meta": "Conversor PDF",
        "has_update": True,
        "containers": ["bentopdf"],
        "actions": {
            "start": {"type": "podman", "containers": ["bentopdf"]},
            "stop":  {"type": "podman", "containers": ["bentopdf"]},
        },
    },
    # Separados para poder dejar el motor encendido (~20 MB) sin el chat (~700 MB)
    "ollama": {
        "label": "Ollama (motor IA)",
        "tab": "locales",
        "port": 11434,
        "url": "http://127.0.0.1:11434",
        "meta": "Modelos locales · lo usan Ofertas, Carrera y candidaturas",
        "has_update": False,
        "containers": ["ollama"],
        "actions": {
            "start": {"type": "script", "path": RUTA_OLLAMA_SCRIPT, "timeout": 60},
            "stop":  {"type": "rm", "containers": ["ollama"]},
        },
    },
    "ia-local": {
        "label": "Open WebUI (chat IA)",
        "tab": "locales",
        "port": 8080,
        "url": "http://127.0.0.1:8080",
        "meta": "Chat en el navegador · arranca Ollama si hace falta",
        "has_update": False,
        "containers": ["openwebui"],
        "actions": {
            "start": {"type": "script", "path": RUTA_IA_SCRIPT, "timeout": 90},
            "stop":  {"type": "rm", "containers": ["openwebui"]},
        },
    },
    "omniroute": {
        "label": "OmniRoute",
        "tab": "locales",
        "port": 20128,
        "url": "http://127.0.0.1:20128",
        "meta": "Router IA · 160+ proveedores",
        "has_update": True,
        "containers": ["omniroute"],
        "actions": {
            "start": {"type": "script", "path": RUTA_OMNIROUTE_SCRIPT, "timeout": 60},
            "stop":  {"type": "podman", "containers": ["omniroute"]},
        },
    },
    "resume": {
        "label": "Reactive Resume",
        "tab": "locales",
        "port": 3004,
        "url": "http://127.0.0.1:3004",
        "meta": "Gestión de CVs",
        "has_update": False,
        "containers": ["reactive-resume"],
        "actions": {
            "start": {"type": "script", "path": RUTA_RESUME_SCRIPT, "timeout": 90},
            "stop":  {"type": "rm", "containers": ["reactive-resume", "resume-chrome", "resume-db"]},
        },
    },
    "obsidian": {
        "label": "Obsidian",
        "tab": "locales",
        "port": None,
        "url": None,
        "meta": "Notas · vault en OneDrive",
        "has_update": True,
        "process": "Obsidian.AppImage",
        "actions": {
            "start": {"type": "process", "binary": RUTA_OBSIDIAN, "args": [RUTA_OBSIDIAN_VAULT]},
            "stop":  {"type": "pkill", "pattern": "Obsidian.AppImage"},
        },
    },
    "pdf-loader": {
        "label": "OpenDataLoader PDF",
        "tab": "locales",
        "port": 5002,
        "url": "http://127.0.0.1:5002/docs",
        "meta": "API de carga de documentos PDF",
        "has_update": False,
        "process": "opendataloader-pdf-hybrid",
        "actions": {
            "start": {"type": "process", "binary": RUTA_PDF_EJECUTABLE, "args": ["--port", "5002"]},
            "stop":  {"type": "pkill", "pattern": "opendataloader", "port": 5002},
        },
    },
    "pyvideo": {
        "label": "pyVideoTrans",
        "tab": "media",
        "port": None,
        "url": None,
        "meta": "Traducción de video local",
        "has_update": False,
        "process": "sp.py",
        "actions": {
            "start": {"type": "script", "path": RUTA_PYVIDEO_SCRIPT},
            "stop":  {"type": "pkill", "pattern": "sp.py"},
        },
    },
    "ace-audio": {
        "label": "Estudio Musical IA",
        "tab": "media",
        "port": 7860,
        "url": "http://127.0.0.1:7860",
        "meta": "Generador de Audio (ACE-Step)",
        "has_update": True,
        "containers": ["ace-audio"],
        "actions": {
            "start": {"type": "ace"},
            "stop":  {"type": "podman", "containers": ["ace-audio"]},
        },
    },
    "metube": {
        "label": "MeTube",
        "tab": "media",
        "port": 8086,
        "url": "http://127.0.0.1:8086",
        "meta": "Descargador YouTube / yt-dlp",
        "has_update": True,
        "process": "metube/app/main.py",
        "actions": {
            "start": {"type": "script", "path": RUTA_METUBE_SCRIPT},
            "stop":  {"type": "pkill", "pattern": "metube/app/main.py", "port": 8086},
        },
    },
    "uptime-kuma": {
        "label": "Uptime Kuma",
        "tab": "sistema",
        "port": 3001,
        "url": "http://127.0.0.1:3001",
        "image": "docker.io/louislam/uptime-kuma:2",
        "meta": "Monitoreo de servicios",
        "has_update": True,
        "containers": ["uptime-kuma"],
        "actions": {
            "start": {"type": "first", "container": "uptime-kuma", "image": "docker.io/louislam/uptime-kuma:latest", "ports": ["3001:3001"], "volumes": ["uptime-kuma_data:/app/data"]},
            "stop":  {"type": "podman", "containers": ["uptime-kuma"]},
        },
    },
    "vaultwarden": {
        "label": "Vaultwarden",
        "tab": "sistema",
        "port": 8585,
        "url": "http://127.0.0.1:8585",
        "image": "docker.io/vaultwarden/server:latest",
        "meta": "Gestor de contraseñas",
        "has_update": True,
        "containers": ["vaultwarden"],
        "actions": {
            "start": {"type": "first", "container": "vaultwarden", "image": "docker.io/vaultwarden/server:latest", "ports": ["8585:80"], "volumes": ["vaultwarden_data:/data"]},
            "stop":  {"type": "podman", "containers": ["vaultwarden"]},
        },
    },
    "scrutiny": {
        "label": "Scrutiny",
        "tab": "sistema",
        "port": 8099,
        "url": "http://127.0.0.1:8099",
        "image": "ghcr.io/analogj/scrutiny:master-omnibus",
        "meta": "Salud de discos S.M.A.R.T.",
        "has_update": True,
        "containers": ["scrutiny"],
        "actions": {
            "start": {"type": "first_scrutiny"},
            "stop":  {"type": "podman", "containers": ["scrutiny"]},
        },
    },
    "onedrive": {
        "label": "OneDrive",
        "tab": "sistema",
        "port": None,
        "url": None,
        "meta": "Sincronización cloud",
        "has_update": False,
        "process": "OneDriveGUI.py",
        "actions": {
            "start": {"type": "process_safe", "binary": os.path.expanduser(os.environ.get("ONEDRIVEGUI_APPIMAGE", "~/Downloads/OneDriveGUI.AppImage")), "args": [], "guard": "OneDriveGUI.py"},
            "stop":  {"type": "pkill", "pattern": "OneDriveGUI"},
        },
    },
    "it-tools": {
        "label": "IT-Tools",
        "tab": "sistema",
        "port": 8084,
        "url": "http://127.0.0.1:8084",
        "image": "docker.io/corentinth/it-tools:latest",
        "meta": "Caja de herramientas para devs",
        "has_update": True,
        "containers": ["it-tools"],
        "actions": {
            "start": {"type": "first", "container": "it-tools", "image": "docker.io/corentinth/it-tools:latest", "ports": ["8084:80"]},
            "stop":  {"type": "podman", "containers": ["it-tools"]},
        },
    },
    "virtualbox": {
        "label": "VirtualBox (labs)",
        "tab": "sistema",
        "port": None,
        "url": None,
        "meta": "Módulos kernel VBox — desactiva KVM",
        "has_update": False,
        "kmod": "vboxdrv",
        "kmod_conflict": "kvm_intel",
        "actions": {
            "start": {"type": "script", "path": RUTA_VBOX_ON},
            "stop":  {"type": "script", "path": RUTA_VBOX_OFF},
        },
    },
    "cowork": {
        "label": "Claude Cowork (vsock)",
        "tab": "sistema",
        "port": None,
        "url": None,
        "meta": "Módulo vhost_vsock — desactiva vsock VMCI de VMware",
        "has_update": False,
        "kmod": "vhost_vsock",
        "kmod_conflict": "vmw_vsock_vmci_transport",
        "actions": {
            "start": {"type": "script", "path": RUTA_COWORK_ON},
            "stop":  {"type": "script", "path": RUTA_COWORK_OFF},
        },
    },
}
