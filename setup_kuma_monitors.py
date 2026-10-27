"""
Crea todos los monitores del panel en Uptime Kuma automáticamente.
Uso: python3 setup_kuma_monitors.py
"""
from uptime_kuma_api import UptimeKumaApi, MonitorType
import getpass
import sys

MONITORS = [
    # ── Podman ──────────────────────────────────────────────────────
    {"name": "Portainer",          "url": "https://localhost:9443",   "interval": 60,  "ignoreTls": True,  "tag": "Podman"},
    {"name": "Paperless-ngx",      "url": "http://localhost:8010",    "interval": 60,  "ignoreTls": False, "tag": "Podman"},
    {"name": "Paperless-AI",       "url": "http://localhost:3030",    "interval": 60,  "ignoreTls": False, "tag": "Podman"},
    {"name": "Immich Photos",      "url": "http://localhost:2283",    "interval": 60,  "ignoreTls": False, "tag": "Podman"},
    {"name": "BentoPDF",           "url": "http://localhost:8081",    "interval": 60,  "ignoreTls": False, "tag": "Podman"},
    # ── Locales ─────────────────────────────────────────────────────
    {"name": "IA Locales (OpenWebUI)", "url": "http://localhost:3003","interval": 120, "ignoreTls": False, "tag": "Locales"},
    {"name": "Reactive Resume",    "url": "http://localhost:3004",    "interval": 60,  "ignoreTls": False, "tag": "Locales"},
    {"name": "OpenDataLoader PDF", "url": "http://localhost:5002/docs","interval": 60, "ignoreTls": False, "tag": "Locales"},
    # ── Media & IA ──────────────────────────────────────────────────
    {"name": "ACE-Step Audio",     "url": "http://127.0.0.1:7860",   "interval": 120, "ignoreTls": False, "tag": "Media"},
    # ── Sistema ─────────────────────────────────────────────────────
    {"name": "Vaultwarden",        "url": "http://localhost:8585",    "interval": 60,  "ignoreTls": False, "tag": "Sistema"},
    {"name": "Scrutiny",           "url": "http://localhost:8099",    "interval": 120, "ignoreTls": False, "tag": "Sistema"},
]

TAG_COLORS = {
    "Podman":   "#00ffc8",
    "Locales":  "#4d9fff",
    "Media":    "#ffb830",
    "Sistema":  "#ff3d5a",
}

def main():
    print("── Configuración de monitores en Uptime Kuma ──")
    username = input("Usuario de Uptime Kuma: ").strip()
    password = getpass.getpass("Contraseña: ")

    print("\nConectando a http://localhost:3001 ...")
    try:
        api = UptimeKumaApi("http://localhost:3001")
        api.login(username, password)
    except Exception as e:
        print(f"❌ Error al conectar/autenticar: {e}")
        sys.exit(1)

    print("✓ Autenticado\n")

    # Crear etiquetas si no existen
    existing_tags = {t["name"]: t["id"] for t in api.get_tags()}
    tag_ids = {}
    for tag_name, color in TAG_COLORS.items():
        if tag_name not in existing_tags:
            result = api.add_tag(name=tag_name, color=color)
            tag_ids[tag_name] = result["id"]
            print(f"  Etiqueta creada: {tag_name}")
        else:
            tag_ids[tag_name] = existing_tags[tag_name]

    # Obtener monitores existentes para no duplicar
    existing_monitors = {m["name"] for m in api.get_monitors()}

    # Crear monitores
    created = 0
    skipped = 0
    for m in MONITORS:
        if m["name"] in existing_monitors:
            print(f"  ⏭  Ya existe: {m['name']}")
            skipped += 1
            continue
        try:
            result = api.add_monitor(
                type=MonitorType.HTTP,
                name=m["name"],
                url=m["url"],
                interval=m["interval"],
                ignoreTls=m["ignoreTls"],
                tags=[{"tag_id": tag_ids[m["tag"]], "value": ""}],
            )
            print(f"  ✓  Creado: {m['name']}  ({m['url']})")
            created += 1
        except Exception as e:
            print(f"  ❌  Error en {m['name']}: {e}")

    api.disconnect()
    print(f"\n── Listo: {created} creados, {skipped} ya existían ──")

if __name__ == "__main__":
    main()
