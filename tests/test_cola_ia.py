"""Cola IA: solo trabaja enchufado, sin llamada y con GPU libre; apaga lo que encendió."""
import cola_ia


def _limpia(monkeypatch, **cond):
    monkeypatch.setattr(cola_ia, "_cola", {})
    monkeypatch.setattr(cola_ia, "log", lambda m: None)
    monkeypatch.setattr(cola_ia, "_enchufado", lambda: cond.get("enchufado", True))
    monkeypatch.setattr(cola_ia, "_en_llamada", lambda: cond.get("llamada", False))
    monkeypatch.setattr(cola_ia, "_vram_libre", lambda: cond.get("vram", 4000))
    monkeypatch.setattr(cola_ia, "_modelo_cargado", lambda: False)
    estado = {"vivo": cond.get("vivo", False), "encendido": 0, "apagado": 0}
    monkeypatch.setattr(cola_ia, "_ollama_vivo", lambda: estado["vivo"])
    def _encender():
        estado["vivo"] = True; estado["encendido"] += 1; return True
    def _apagar():
        estado["vivo"] = False; estado["apagado"] += 1; return True
    monkeypatch.setattr(cola_ia, "_encender", _encender)
    monkeypatch.setattr(cola_ia, "_apagar", _apagar)
    return estado


def test_no_duplica_la_misma_clave(monkeypatch):
    _limpia(monkeypatch)
    assert cola_ia.encolar("a", "uno", lambda: None) is True
    assert cola_ia.encolar("a", "uno otra vez", lambda: None) is False
    assert cola_ia.pendientes() == ["uno"]


def test_enciende_hace_y_apaga(monkeypatch):
    estado = _limpia(monkeypatch)
    hechos = []
    cola_ia.encolar("a", "uno", lambda: hechos.append(1))
    cola_ia.encolar("b", "dos", lambda: hechos.append(2))
    cola_ia._tanda()
    assert hechos == [1, 2] and not cola_ia._cola
    assert estado["encendido"] == 1 and estado["apagado"] == 1


def test_si_ya_estaba_encendido_no_lo_apaga(monkeypatch):
    estado = _limpia(monkeypatch, vivo=True)
    cola_ia.encolar("a", "uno", lambda: None)
    cola_ia._tanda()
    assert estado["encendido"] == 0 and estado["apagado"] == 0


def test_espera_con_bateria_llamada_o_gpu_ocupada(monkeypatch):
    for cond in ({"enchufado": False}, {"llamada": True}, {"vram": 500}):
        estado = _limpia(monkeypatch, **cond)
        hechos = []
        cola_ia.encolar("a", "uno", lambda: hechos.append(1))
        cola_ia._tanda()
        assert hechos == [] and len(cola_ia._cola) == 1 and estado["encendido"] == 0


def test_un_fallo_no_para_la_cola(monkeypatch):
    _limpia(monkeypatch)
    hechos = []
    cola_ia.encolar("a", "rompe", lambda: 1 / 0)
    cola_ia.encolar("b", "sigue", lambda: hechos.append(2))
    cola_ia._tanda()
    assert hechos == [2] and not cola_ia._cola


def test_ofertas_encola_las_mejores_sin_evaluar(monkeypatch):
    import ofertas
    _limpia(monkeypatch)
    items = {
        "a": {"id": "a", "titulo": "Sysadmin", "relevancia": 90},
        "b": {"id": "b", "titulo": "Ya evaluada", "relevancia": 95, "eval": {"encaje": 70}},
        "c": {"id": "c", "titulo": "Descartada", "relevancia": 80, "estado": "descartada"},
        "d": {"id": "d", "titulo": "Poco relevante", "relevancia": 10},
        "e": {"id": "e", "titulo": "Técnico redes", "relevancia": 60},
    }
    monkeypatch.setattr(ofertas, "_load", lambda: {"items": items})
    ofertas.encolar_evaluaciones()
    assert list(cola_ia._cola) == ["oferta:a", "oferta:e", "ofertas:aviso"]


def test_json_de_tolera_bloque_de_codigo():
    from rag import _json_de
    assert _json_de('```json\n{"a": 1}\n```') == {"a": 1}
    assert _json_de('{"a": 1}') == {"a": 1}
    assert _json_de("") == {}


def test_becas_clasifica_y_conserva_al_refrescar(monkeypatch, tmp_path):
    import becas, rag
    _limpia(monkeypatch)
    monkeypatch.setattr(becas, "DATA_FILE", str(tmp_path / "becas.json"))
    monkeypatch.setattr(becas, "log", lambda m: None)
    hoy = __import__("datetime").date.today().isoformat()
    base = {"kind": "telegram", "first_seen": hoy, "new": True, "provider": "x", "tags": []}
    becas._save({"items": [{**base, "id": "1", "title": "CCNA gratis 100% off", "url": "u1"},
                           {**base, "id": "2", "title": "Curso de cocina", "url": "u2"},
                           {**base, "id": "c", "title": "Catálogo", "url": "u3", "kind": "curado", "new": False}]})
    monkeypatch.setattr(rag, "_ollama_post", lambda *a, **k: {"message": {"content":
        '```json\n{"r": [{"n": 1, "v": "sirve", "motivo": "CCNA gratis"}, {"n": 2, "v": "basura", "motivo": "no es IT"}]}\n```'}})
    becas.encolar_clasificaciones()
    assert list(cola_ia._cola) == ["becas:1", "becas:aviso"]     # el curado no se clasifica
    assert becas.clasificar(["1", "2"]) == 2
    items = {i["id"]: i for i in becas._load()["items"]}
    assert items["1"]["ia"]["v"] == "sirve" and items["2"]["ia"]["v"] == "basura"
    assert becas.get_data()["nuevos"] == 1                       # la basura no cuenta como nueva
    assert becas._sin_clasificar() == []


def test_ingles_va_detras_de_las_evaluaciones(monkeypatch):
    import ingles, ofertas
    _limpia(monkeypatch)
    monkeypatch.setattr(ofertas, "_load", lambda: {"items": {"a": {"id": "a", "titulo": "Sysadmin", "relevancia": 90}}})
    ofertas.encolar_evaluaciones()
    ingles.encolar_extraccion()
    assert list(cola_ia._cola) == ["oferta:a", "ofertas:aviso", "ingles:extraer"]
