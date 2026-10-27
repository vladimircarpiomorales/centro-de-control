#!/bin/bash
# Vuelve a VMware descargando vhost_vsock (Cowork)
sudo modprobe -r vhost_vsock 2>/dev/null || true
sudo modprobe vmw_vsock_vmci_transport 2>/dev/null || true
echo "VMware vsock (VMCI) activado"
