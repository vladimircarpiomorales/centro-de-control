"""La calculadora de neto: coherente aunque sea una estimación."""
import sueldo


def test_neto_crece_con_el_bruto():
    netos = [sueldo.neto(b)["neto_anual"] for b in range(12000, 90001, 1500)]
    assert netos == sorted(netos)


def test_sueldo_bajo_no_paga_irpf():
    assert sueldo.neto(15000)["irpf"] == 0


def test_rango_razonable_30k():
    r = sueldo.neto(30000, 14)
    assert 22500 < r["neto_anual"] < 24500
    assert abs(r["neto_mes"] * 14 - r["neto_anual"]) < 1


def test_comparar_marca_la_mejor():
    res = sueldo.comparar([{"nombre": "A", "bruto": 30000, "dias_oficina": 5, "coste_desplazamiento": 6},
                           {"nombre": "B", "bruto": 29000, "dias_oficina": 0, "extras": 1100}])
    mejor = [r for r in res if r["diferencia"] == 0]
    assert len(mejor) == 1 and mejor[0]["nombre"] == "B"
