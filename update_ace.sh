#!/bin/bash
echo "🔨 Construyendo imagen de ACE-Step 1.5 (esto tardará unos minutos)..."

cd ~/MiPanelControl/build-ace

# Reconstruir la imagen
podman build -t ace-audio:latest .

echo "✅ Imagen construida. Reiniciando el contenedor..."

# Limpiar contenedor viejo si existe
podman stop ace-audio 2>/dev/null || true
podman rm -f ace-audio 2>/dev/null || true

# Crear carpetas en el host si no existen
mkdir -p ~/Music/ACE-Audio/generados

# Lanzar contenedor con GPU y volúmenes
podman run -d \
  --name ace-audio \
  --device nvidia.com/gpu=all \
  --network host \
  -e ACESTEP_DTYPE=float32 \
  -v ~/Music/ACE-Audio/generados:/generados \
  -v ace-step-checkpoints:/app/checkpoints \
  ace-audio:latest

echo "🎵 Estudio Musical IA listo y corriendo."
