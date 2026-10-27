#!/bin/bash
# Vuelve a KVM descargando VirtualBox
sudo modprobe -r vboxnetadp vboxnetflt vboxdrv 2>/dev/null || true
sudo modprobe kvm
sudo modprobe kvm_intel
echo "KVM/VMM activado"
