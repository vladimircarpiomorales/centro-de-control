#!/bin/bash
# Solo el motor: lo usan Ofertas, Carrera, candidaturas (respaldo) y Open WebUI.
# Se puede llamar aunque ya esté en marcha.
CONTAINER="ollama"

if podman container exists "$CONTAINER" 2>/dev/null; then
    echo "Contenedor existe, arrancando..."
    podman start "$CONTAINER"
else
    echo "Iniciando motor Ollama con GPU..."
    # red del host (necesaria para la GPU y para hablar con OmniRoute), pero escuchando solo
    # en 127.0.0.1: con 0.0.0.0 cualquiera en la WiFi podía usar los modelos
    podman run -d --name "$CONTAINER" \
        --device nvidia.com/gpu=all \
        --network=host \
        -e OLLAMA_HOST=127.0.0.1:11434 \
        -v $HOME/ollama_data:/root/.ollama \
        docker.io/ollama/ollama:latest
fi

echo "Ollama disponible en http://127.0.0.1:11434"
