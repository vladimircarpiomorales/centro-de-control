#!/bin/bash
# Activa Cowork (vhost_vsock) descargando el transporte VMCI de VMware (incompatibles)
sudo modprobe -r vmw_vsock_vmci_transport 2>/dev/null || true
sudo modprobe vhost_vsock 2>/dev/null
echo "Cowork (vhost_vsock) activado"
