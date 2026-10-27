import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# las pruebas usan la persona ficticia de perfil.example.json, nunca un perfil real
os.environ["PERFIL_FILE"] = os.path.join(RAIZ, "perfil.example.json")
os.environ.setdefault("EXTENSION_ID", "abcdefghijklmnopabcdefghijklmnop")
# los mensajes de las pruebas van a un log aparte, no al panel.log de verdad
import tempfile
os.environ["LOG_FILE"] = os.path.join(tempfile.gettempdir(), "mipanelcontrol-pruebas.log")
sys.path.insert(0, RAIZ)
MUESTRAS = os.path.join(RAIZ, "tests", "muestras")


def muestra(nombre: str) -> str:
    ruta = os.path.join(MUESTRAS, nombre)
    if not os.path.isfile(ruta):
        import pytest
        # el repositorio público no trae las páginas guardadas (son contenido de terceros)
        pytest.skip(f"falta tests/muestras/{nombre}: python tests/actualizar_muestras.py")
    with open(ruta, encoding="utf-8") as f:
        return f.read()
