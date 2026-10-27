"""Lo que evita que la IA te haga decir cosas falsas o te enseñe inglés mal."""
import candidatura
import ingles
import salud_fuentes

CV = "Nube Norte: Azure, Intune. Redes del Sur: Cisco, VLAN. 40+ usuarios. AZ-104 y CCNA en preparación."
OFERTA = "Se requiere VCP, HPS, Prisma Access y PAM. Guardias puntuales."


def _prep(texto):
    return {"perfil": texto, "carta": "", "encaje": [], "huecos": [], "preguntas": [], "preguntas_en": []}


def test_detecta_empresa_cambiada():
    avisos = candidatura._revisar(_prep("En Redes del Sur administraba Azure e Intune."), CV, OFERTA)
    assert any("Empresa cambiada" in a for a in avisos)


def test_detecta_certificacion_inventada_en_preparacion():
    avisos = candidatura._revisar(_prep("Estoy preparando la VCP."), CV, OFERTA, solo_precisas=True)
    assert any("VCP" in a for a in avisos)


def test_detecta_etapa_cerrada_en_presente():
    avisos = candidatura._revisar(_prep("I currently work for Nube Norte."), CV, OFERTA, solo_precisas=True)
    assert any("presente" in a for a in avisos)


def test_negar_algo_no_es_inventar():
    avisos = candidatura._revisar(_prep("No he trabajado con Prisma Access ni con PAM."), CV, OFERTA)
    assert not avisos


def test_duracion_inventada_aunque_el_numero_exista():
    assert "40 minutos" in candidatura._cifras_dudosas("lo resolví en 40 minutos", CV)
    assert not candidatura._cifras_dudosas("migré a 40+ usuarios", CV)


def test_ingles_descarta_traduccion_que_es_espanol():
    desc = "Buscamos persona para cubrir guardias puntuales y soporte de servidores."
    malas = [{"es": "soporte de servidores", "en": "soporte de servidores"},     # sin traducir
             {"es": "frase que no está", "en": "server support"},                # no está en la oferta
             {"es": "guardias puntuales", "en": "occasional on-call duty"}]      # buena
    validos = ingles._terminos_es(desc, malas)
    assert [v["en"] for v in validos] == ["occasional on-call duty"]


def test_ingles_detecta_idioma():
    assert ingles._idioma("Buscamos administrador de sistemas con experiencia en Linux") == "es"
    assert ingles._idioma("We are looking for a sysadmin with experience in Linux and our team") == "en"


def test_fuente_rota(tmp_path, monkeypatch):
    monkeypatch.setattr(salud_fuentes, "FICHERO", str(tmp_path / "f.json"))
    for n in (12, 9, 0):
        salud_fuentes.registrar("x", "X", n)
    assert not salud_fuentes.estado()["x"]["rota"]          # un cero suelto no
    salud_fuentes.registrar("x", "X", 0)
    assert salud_fuentes.estado()["x"]["rota"]              # dos seguidos sí
    salud_fuentes.registrar("nueva", "N", 0)
    salud_fuentes.registrar("nueva", "N", 0)
    assert not salud_fuentes.estado()["nueva"]["rota"]      # nunca trajo nada: no se sabe


def test_laboratorios_no_acepta_rutas_inventadas():
    import laboratorios
    assert laboratorios._vmx_de("../../etc/passwd") == ""
    assert laboratorios._vmx_de('vmlist1.config = "x"') == ""


def test_captcha_no_cuenta_como_lector_roto(tmp_path, monkeypatch):
    monkeypatch.setattr(salud_fuentes, "FICHERO", str(tmp_path / "f.json"))
    salud_fuentes.registrar("ij", "InfoJobs", 25)
    salud_fuentes.registrar("ij", "InfoJobs", 0, motivo="captcha")
    salud_fuentes.registrar("ij", "InfoJobs", 0, motivo="captcha")
    e = salud_fuentes.estado()["ij"]
    assert e["rota"] and e["motivo"] == "captcha"
