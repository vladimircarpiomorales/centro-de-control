"""Los lectores de portales contra páginas reales guardadas (tests/muestras).
Si un portal cambia: arreglar el lector, `python tests/actualizar_muestras.py`
y que esto vuelva a pasar."""
import pytest

import becas
import ofertas
from conftest import muestra


def _con_pagina(monkeypatch, modulo, nombre):
    monkeypatch.setattr(modulo, "_http_get", lambda *a, **k: muestra(nombre))


def _ofertas_validas(items):
    assert len(items) >= 3, "el lector apenas encuentra ofertas: ¿ha cambiado el HTML?"
    for it in items:
        assert it["titulo"].strip()
        assert it["nid"]
        assert it["url"].startswith("http")


def test_infojobs(monkeypatch):
    if 'id="job-title-' not in muestra("infojobs.html"):
        pytest.skip("la muestra de InfoJobs es un captcha: `python tests/actualizar_muestras.py` más tarde")
    _con_pagina(monkeypatch, ofertas, "infojobs.html")
    _ofertas_validas(ofertas._infojobs("administrador de sistemas"))


def test_tecnoempleo(monkeypatch):
    _con_pagina(monkeypatch, ofertas, "tecnoempleo.html")
    _ofertas_validas(ofertas._tecnoempleo("administrador de sistemas"))


def test_linkedin(monkeypatch):
    _con_pagina(monkeypatch, ofertas, "linkedin.html")
    items = ofertas._linkedin("administrador de sistemas", "Madrid")
    _ofertas_validas(items)
    assert all(it["modalidad"] == "" for it in items)


def test_linkedin_remoto_con_sede_en_madrid_no_es_remoto(monkeypatch):
    # f_WT=2 cuela presenciales: con sede en Madrid la modalidad queda sin marcar
    _con_pagina(monkeypatch, ofertas, "linkedin.html")
    for it in ofertas._linkedin("x", "Spain", remoto=True):
        if ofertas._MADRID.search(it["ubicacion"]):
            assert it["modalidad"] == ""


def test_telegram(monkeypatch):
    _con_pagina(monkeypatch, becas, "telegram.html")
    items = becas._fetch_telegram({"chan": "udemy_free_coupon", "name": "x", "filtrar": False})
    assert items, "el lector de Telegram no encuentra mensajes"
    assert all(i["url"].startswith("https://t.me/") for i in items)


def test_reddit(monkeypatch):
    _con_pagina(monkeypatch, becas, "reddit.xml")
    items = becas._fetch_reddit("r/udemyfreebies", "https://x", filtrar=False)
    assert items and all(i["url"].startswith("http") for i in items)


def test_infojobs_captcha_se_avisa(monkeypatch):
    monkeypatch.setattr(ofertas, "_http_get", lambda *a, **k: "<html>Please solve the captcha</html>")
    with pytest.raises(RuntimeError, match="captcha"):
        ofertas._infojobs("x")
