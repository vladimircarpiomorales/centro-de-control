#!/bin/bash
echo "Iniciando red de Reactive Resume..."
podman network create resume-net 2>/dev/null

echo "Iniciando Base de Datos..."
podman run -d --replace --name resume-db --network resume-net \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=resume \
  -v resume_db_data:/var/lib/postgresql/data \
  docker.io/library/postgres:15-alpine

echo "Iniciando motor de PDF..."
podman run -d --replace --name resume-chrome --network resume-net \
  docker.io/browserless/chrome:latest

echo "Esperando 5 segundos a que la BD esté lista..."
sleep 5

echo "Iniciando Reactive Resume..."
podman run -d --replace --name reactive-resume --network resume-net \
  -p 3004:3000 \
  -e APP_URL=http://localhost:3004 \
  -e DATABASE_URL=postgresql://postgres:postgres@resume-db:5432/resume \
  -e CHROME_URL=ws://resume-chrome:3000 \
  -e AUTH_SECRET=super_secreta_clave_pro_123 \
  docker.io/amruthpillai/reactive-resume:latest

echo "¡Reactive Resume iniciado con éxito en el puerto 3004!"
