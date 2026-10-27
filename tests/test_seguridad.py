"""El panel solo obedece a sí mismo y a la extensión de Brave."""
import pytest


@pytest.fixture(scope="module")
def cliente():
    import api, becas, ofertas, ingles, copias, mantenimiento, status
    # sin los hilos de fondo (buscan en internet, hacen copias…)
    for mod, fn in ((status, "start_notification_monitor"), (becas, "start_becas_monitor"),
                    (ofertas, "start_ofertas_monitor"), (ingles, "start_audio_precalentar"),
                    (copias, "start_copias"), (mantenimiento, "start_mantenimiento")):
        setattr(mod, fn, lambda: None)
    api.start_notification_monitor = lambda: None
    app = api.create_app()
    app.testing = True
    return app.test_client()

PANEL = {"Host": "127.0.0.1:7788", "Origin": "http://127.0.0.1:7788"}


def test_web_ajena_no_puede_dar_ordenes(cliente):
    r = cliente.post("/api/ingles/borrar", data="{}", content_type="text/plain",
                     headers={"Host": "127.0.0.1:7788", "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_dns_rebinding_bloqueado(cliente):
    r = cliente.get("/api/ingles", headers={"Host": "evil.example:7788"})
    assert r.status_code == 403


def test_extension_de_brave_si_puede(cliente):
    r = cliente.post("/api/descargas/sonda", json={},
                     headers={"Host": "127.0.0.1:7788", "Origin": "chrome-extension://" + __import__("os").environ["EXTENSION_ID"]})
    assert r.status_code == 400   # pasa el filtro; falla después por no mandar url


def test_manuales_no_sirve_ficheros_que_no_son_md(cliente):
    import os
    r = cliente.get("/api/manuales/raw?path=" + os.path.expanduser("~/.bashrc"), headers=PANEL)
    assert r.status_code == 400


def test_mantenimiento_solo_acciones_de_la_lista(cliente):
    r = cliente.post("/api/mantenimiento/accion", json={"accion": "rm -rf"}, headers=PANEL)
    assert r.status_code == 400


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("get", "/api/manuales?dir=/tmp", None),
    ("get", "/api/manuales/buscar?dir=/etc&q=root", None),
    ("post", "/api/manuales/rag/index", {"dir": "/tmp"}),
    ("post", "/api/manuales/rag/ask", {"dir": "/tmp", "pregunta": "hola"}),
])
def test_manuales_solo_carpetas_de_home_o_de_manuales(cliente, metodo, ruta, cuerpo):
    r = getattr(cliente, metodo)(ruta, json=cuerpo, headers=PANEL) if cuerpo else getattr(cliente, metodo)(ruta, headers=PANEL)
    assert r.status_code == 400


def test_manuales_prefijo_parecido_al_home_no_cuela(cliente, tmp_path):
    import os
    home = os.path.realpath(os.path.expanduser("~"))
    r = cliente.get("/api/manuales/raw?path=" + home + "2/notas.md", headers=PANEL)
    assert r.status_code == 400


def test_rag_no_usa_pickle():
    import pathlib
    import rag
    assert rag.INDEX_FILENAME.endswith(".json")
    codigo = pathlib.Path(rag.__file__).read_text()
    assert "import pickle" not in codigo and "pickle.load" not in codigo
