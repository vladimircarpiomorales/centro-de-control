#!/bin/bash
# Activa VirtualBox descargando KVM (incompatibles)
sudo modprobe -r kvm_intel kvm 2>/dev/null || true
sudo modprobe vboxdrv 2>/dev/null
sudo modprobe vboxnetflt 2>/dev/null || true
sudo modprobe vboxnetadp 2>/dev/null || true
echo "VirtualBox activado"
