"""
Centro de Control PRO — perfil.py
Lo personal del usuario fuera del código: perfil.json (privado, en .gitignore).
Si no existe se usa perfil.example.json (una persona ficticia), así el proyecto
funciona recién clonado y el repositorio público no lleva datos de nadie.

  empresas        → dónde hizo cada cosa (lo usan el prompt y el revisor de candidaturas)
  en_preparacion  → únicas certificaciones que puede decir que prepara
  reglas          → reglas propias de su CV (título, idioma…)
  cerrada: true   → empresa de la que se habla siempre en pasado
"""

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def _ruta() -> str:
    propio = os.environ.get("PERFIL_FILE") or os.path.join(BASE, "perfil.json")
    return propio if os.path.isfile(propio) else os.path.join(BASE, "perfil.example.json")

def get() -> dict:
    with open(_ruta(), encoding="utf-8") as f:
        p = json.load(f)
    p.setdefault("empresas", {})
    p.setdefault("en_preparacion", [])
    p.setdefault("reglas", [])
    return p

def cerradas() -> list:
    return [nombre for nombre, d in get()["empresas"].items() if d.get("cerrada")]
