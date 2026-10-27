#!/bin/bash
# La clave de OmniRoute vive en .env (fuera de git); se lee aquí para que
# el script funcione igual lanzado desde el panel que a mano.
DIR=$(dirname "$(readlink -f "$0")")
OMNIROUTE_API_KEY="${OMNIROUTE_API_KEY:-$(grep -m1 '^OMNIROUTE_API_KEY=' "$DIR/.env" | cut -d= -f2-)}"

# Open WebUI necesita el motor; si ya está en marcha, ollama-up.sh no hace nada
bash "$DIR/ollama-up.sh"

podman rm -f openwebui >/dev/null 2>&1
echo "Iniciando Open WebUI..."
podman run -d --name openwebui \
    --network=host \
    -e HOST=127.0.0.1 \
    -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    -e OPENAI_API_BASE_URL=http://127.0.0.1:20128/v1 \
    -e OPENAI_API_KEY="$OMNIROUTE_API_KEY" \
    -v $HOME/openwebui_data:/app/backend/data \
    -v $HOME/Proyectos:$HOME/Proyectos:Z \
    ghcr.io/open-webui/open-webui:main

echo "Open WebUI iniciado — Ollama: :11434 | Open WebUI: :8080"
