"""
Centro de Control PRO — almacen.py
Cómo guardan sus datos todos los módulos del panel.

- guardar_json: escribe en «archivo.tmp», lo vuelca a disco y lo renombra encima del
  bueno. Si el equipo se apaga a mitad, queda el archivo anterior entero, nunca uno
  cortado.
- en_exclusiva: envuelve una función que lee, cambia y guarda con el candado de su
  módulo. Así dos peticiones a la vez no se pisan: la segunda espera y lee lo que
  dejó la primera. El candado de cada módulo es un RLock porque su _save vuelve a
  cogerlo dentro.

Las funciones que esperan a la IA o a internet NO se envuelven enteras (bloquearían
el módulo minutos): hacen la parte lenta fuera y después, bajo el candado, vuelven a
leer, aplican su cambio y guardan.
"""

import functools
import json
import os


def guardar_json(ruta: str, datos, indent=1):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def en_exclusiva(candado):
    def decorador(fn):
        @functools.wraps(fn)
        def envoltura(*args, **kwargs):
            with candado:
                return fn(*args, **kwargs)
        return envoltura
    return decorador
