#!/bin/bash
set -e

CONTAINER="omniroute"
IMAGE="docker.io/diegosouzapw/omniroute:latest"

if podman container exists "$CONTAINER" 2>/dev/null; then
    echo "Contenedor existe, arrancando..."
    podman start "$CONTAINER"
else
    echo "Primera vez: creando contenedor OmniRoute..."
    podman run -d \
        --name "$CONTAINER" \
        --stop-timeout 40 \
        -p 127.0.0.1:20128:20128 \
        -v omniroute-data:/app/data \
        "$IMAGE"
fi

echo "OmniRoute disponible en http://localhost:20128"
