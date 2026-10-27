"""El panel solo dice «hecho» si los comandos salieron bien, y no rompe un servicio que funcionaba."""
import subprocess

import pytest

import actions


class PodmanFalso:
    """Apunta cada orden y falla en las que contengan alguna de las palabras de `falla`."""
    def __init__(self, falla=()):
        self.ordenes, self.falla = [], falla

    def __call__(self, args, **kwargs):
        orden = " ".join(map(str, args)); self.ordenes.append(orden)
        rc = 1 if any(p in orden for p in self.falla) else 0
        return subprocess.CompletedProcess(args, rc, stdout="", stderr="Error: sin conexión al registro" if rc else "")


@pytest.fixture
def entorno(monkeypatch):
    registro = []
    monkeypatch.setattr(actions, "log", registro.append)
    monkeypatch.setattr(actions.socketio, "emit", lambda *a, **k: None)
    monkeypatch.setattr(actions, "invalidate_status_cache", lambda: None)
    def con(podman):
        monkeypatch.setattr(actions.subprocess, "run", podman)
        return registro
    return con


def test_si_la_descarga_falla_no_se_toca_el_servicio(entorno):
    podman = PodmanFalso(falla=["pull"]); registro = entorno(podman)
    actions._do_update("vaultwarden")
    assert not any(o.startswith(("podman stop", "podman rm", "podman run")) for o in podman.ordenes)
    assert any("❌" in l and "descargar" in l for l in registro)
    assert not any(l.startswith("✓") for l in registro)


def test_actualizacion_buena_baja_primero_y_dice_hecho(entorno):
    podman = PodmanFalso(); registro = entorno(podman)
    actions._do_update("vaultwarden")
    pull = next(i for i, o in enumerate(podman.ordenes) if o.startswith("podman pull"))
    stop = next(i for i, o in enumerate(podman.ordenes) if o.startswith("podman stop"))
    assert pull < stop
    assert registro[-1].startswith("✓")


def test_si_falla_crear_el_contenedor_no_dice_hecho(entorno):
    podman = PodmanFalso(falla=["podman run"]); registro = entorno(podman)
    actions._do_update("it-tools")
    assert any("❌" in l and "crear el contenedor it-tools" in l for l in registro)
    assert not any(l.startswith("✓") for l in registro)


def test_grupo_dice_que_contenedor_fallo(entorno):
    podman = PodmanFalso(falla=["paperless-redis"]); registro = entorno(podman)
    actions._toggle("paperless", "start")
    assert any("❌" in l and "paperless-redis" in l for l in registro)
    assert not any("iniciado" in l for l in registro)


def test_immich_actualiza_tambien_el_servidor(entorno):
    podman = PodmanFalso(); entorno(podman)
    actions._do_update("immich")
    assert "podman pull ghcr.io/immich-app/immich-server:release" in podman.ordenes
