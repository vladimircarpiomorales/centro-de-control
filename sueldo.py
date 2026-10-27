"""
Centro de Control PRO — sueldo.py
De bruto a neto en España (residente en Madrid) y comparador de ofertas.

ES UNA ESTIMACIÓN con los parámetros de 2025: contrato general indefinido,
soltero/a sin hijos ni discapacidad, sin otras rentas. Sirve sobre todo para
COMPARAR ofertas entre sí (el error afecta igual a todas). La retención real de
la nómina puede diferir; lo que manda es la declaración de la renta.

  Seguridad Social del trabajador: contingencias comunes 4,70 % + desempleo 1,55 %
    + formación 0,10 % + MEI 0,13 % = 6,48 %, con base máxima 4.909,50 €/mes.
  IRPF: rendimiento neto = bruto − SS − 2.000 € (otros gastos);
    reducción por rendimientos del trabajo (art. 20 LIRPF);
    cuota = escala estatal + escala de Madrid sobre la base, menos las mismas
    escalas aplicadas al mínimo personal (5.550 €).
"""

ANIO = 2025
SS_TIPO = 0.0648
SS_BASE_MAX_ANUAL = 4909.50 * 12
GASTOS_GENERALES = 2000
MINIMO_PERSONAL = 5550

ESCALA_ESTATAL = [(12450, 0.095), (20200, 0.12), (35200, 0.15), (60000, 0.185), (300000, 0.225), (None, 0.245)]
ESCALA_MADRID = [(13362.22, 0.085), (19004.63, 0.107), (35425.68, 0.128), (57320.40, 0.174), (None, 0.205)]


def _escala(base: float, tramos: list) -> float:
    cuota, desde = 0.0, 0.0
    for hasta, tipo in tramos:
        if base <= desde:
            break
        tramo = (min(base, hasta) if hasta else base) - desde
        cuota += tramo * tipo
        if hasta is None:
            break
        desde = hasta
    return cuota

def _reduccion_trabajo(rn: float) -> float:
    if rn <= 14852:
        return 7302
    if rn <= 17673.52:
        return 7302 - 1.75 * (rn - 14852)
    if rn <= 19747.5:
        return 2364.34 - 1.14 * (rn - 17673.52)
    return 0.0

def neto(bruto: float, pagas: int = 14) -> dict:
    bruto = max(0.0, float(bruto))
    pagas = 14 if int(pagas) == 14 else 12
    ss = min(bruto, SS_BASE_MAX_ANUAL) * SS_TIPO
    rn = max(0.0, bruto - ss - GASTOS_GENERALES)
    base = max(0.0, rn - _reduccion_trabajo(rn))
    cuota = 0.0
    for escala in (ESCALA_ESTATAL, ESCALA_MADRID):
        cuota += max(0.0, _escala(base, escala) - _escala(min(MINIMO_PERSONAL, base), escala))
    neto_anual = bruto - ss - cuota
    return {"anio": ANIO, "bruto": round(bruto, 2), "pagas": pagas,
            "ss": round(ss, 2), "irpf": round(cuota, 2), "neto_anual": round(neto_anual, 2),
            "neto_mes": round(neto_anual / pagas, 2), "neto_mes_12": round(neto_anual / 12, 2),
            "tipo_irpf": round(100 * cuota / bruto, 1) if bruto else 0,
            "tipo_total": round(100 * (ss + cuota) / bruto, 1) if bruto else 0}

def comparar(ofertas: list) -> list:
    """Cada oferta: {nombre, bruto, pagas, extras (€/año exentos: ticket, seguro…),
    dias_oficina (por semana), coste_desplazamiento (€ por día de oficina)}."""
    salida = []
    for o in ofertas[:4]:
        try:
            r = neto(float(o.get("bruto") or 0), int(o.get("pagas") or 14))
        except (TypeError, ValueError):
            continue
        extras = max(0.0, float(o.get("extras") or 0))
        dias = max(0.0, min(5.0, float(o.get("dias_oficina") or 0)))
        desplaz = max(0.0, float(o.get("coste_desplazamiento") or 0))
        coste_oficina = dias * desplaz * 46          # ~46 semanas laborables al año
        r.update({"nombre": str(o.get("nombre") or "Oferta")[:40], "extras": extras,
                  "coste_oficina": round(coste_oficina, 2),
                  "valor_real": round(r["neto_anual"] + extras - coste_oficina, 2)})
        salida.append(r)
    mejor = max((r["valor_real"] for r in salida), default=0)
    for r in salida:
        r["diferencia"] = round(r["valor_real"] - mejor, 2)
    return salida
