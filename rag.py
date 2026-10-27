"""
RAG (búsqueda semántica + chat) sobre los manuales convertidos, 100% local via Ollama.
"""

import glob
import json
import os
import re
import time
import urllib.request

from services import RUTA_MANUALES_MD

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODELO_EMBEDDING = "nomic-embed-text"
MODELO_CHAT_DEFAULT = "llama3.1"
# JSON y no pickle: el índice vive en una carpeta que llega desde fuera, y cargar un pickle
# ajeno puede ejecutar código. Solo guarda texto, números y listas.
INDEX_FILENAME = ".rag_index.json"


def _ollama_post(path: str, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _json_de(texto: str) -> dict:
    """JSON de la respuesta de un modelo. Aunque se pida format=json, qwen3.5 y Claude
    a veces lo envuelven en ```json … ```."""
    texto = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", (texto or "").strip())
    return json.loads(texto[texto.find("{"):texto.rfind("}") + 1] or "{}")

def _json_ollama(r: dict) -> dict:
    return _json_de(r.get("message", {}).get("content", ""))


def _embed(texto: str) -> list:
    r = _ollama_post("/api/embeddings", {"model": MODELO_EMBEDDING, "prompt": texto})
    return r["embedding"]


def _chunkear(texto: str, max_chars: int = 1800, overlap: int = 200):
    """Fragmenta por párrafos/encabezados, agrupando hasta max_chars con un poco de solape."""
    texto = re.sub(r"<!--\s*image\s*-->", "", texto)
    texto = re.sub(r"!\[[^\]]*\]\(.+\)", "", texto)
    partes = re.split(r"\n(?=#{1,3} )|\n{2,}", texto)
    partes = [p.strip() for p in partes if p.strip()]

    chunks = []
    actual = ""
    for parte in partes:
        if len(actual) + len(parte) + 1 <= max_chars:
            actual = f"{actual}\n{parte}" if actual else parte
        else:
            if actual:
                chunks.append(actual)
            cola = actual[-overlap:] if actual else ""
            actual = f"{cola}\n{parte}" if cola else parte
    if actual:
        chunks.append(actual)
    return chunks


def _index_path(base_dir: str) -> str:
    return os.path.join(base_dir, INDEX_FILENAME)


def _cargar_index(base_dir: str) -> dict:
    path = _index_path(base_dir)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _guardar_index(base_dir: str, index: dict):
    path = _index_path(base_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f)
    os.replace(tmp, path)


def indexar(base_dir: str = RUTA_MANUALES_MD, callback_log=None, forzar=False):
    """Genera embeddings de todos los .md nuevos/cambiados en base_dir. Se puede volver a
    llamar cuando quieras — solo procesa lo que cambió desde la última vez (por mtime)."""

    def log(msg):
        if callback_log:
            callback_log(msg)
        else:
            print(msg)

    base_dir = os.path.abspath(os.path.expanduser(base_dir))
    index = {} if forzar else _cargar_index(base_dir)

    archivos = sorted(glob.glob(os.path.join(base_dir, "*.md")))
    if not archivos:
        log("⚠ No hay manuales para indexar.")
        return

    total_nuevos = 0
    for archivo in archivos:
        nombre = os.path.splitext(os.path.basename(archivo))[0]
        mtime = os.path.getmtime(archivo)
        existente = index.get(archivo)
        if existente and existente.get("mtime") == mtime:
            continue

        log(f"🧠 Indexando {nombre}...")
        with open(archivo, encoding="utf-8") as f:
            contenido = f.read()
        chunks = _chunkear(contenido)

        embeddings = []
        for i, chunk in enumerate(chunks):
            embeddings.append(_embed(chunk))
            if (i + 1) % 20 == 0:
                log(f"  · {nombre}: {i + 1}/{len(chunks)} fragmentos")

        index[archivo] = {"nombre": nombre, "mtime": mtime, "chunks": chunks, "embeddings": embeddings}
        total_nuevos += 1
        log(f"✅ {nombre} indexado — {len(chunks)} fragmentos")

    _guardar_index(base_dir, index)
    if total_nuevos:
        log(f"📊 Índice RAG actualizado — {total_nuevos} manual(es) nuevo(s)/cambiado(s).")
    else:
        log("✓ Índice RAG ya estaba al día.")


def _coseno(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def preguntar(pregunta: str, base_dir: str = RUTA_MANUALES_MD, modelo: str = MODELO_CHAT_DEFAULT, top_k: int = 3):
    """Busca los fragmentos más relevantes en el índice y le pide al modelo que responda usándolos."""
    base_dir = os.path.abspath(os.path.expanduser(base_dir))
    index = _cargar_index(base_dir)
    if not index:
        return {
            "respuesta": "Todavía no hay manuales indexados en esta carpeta. Indexa primero.",
            "fuentes": [],
        }

    pregunta_emb = _embed(pregunta)

    candidatos = []
    for archivo, datos in index.items():
        for chunk, emb in zip(datos["chunks"], datos["embeddings"]):
            candidatos.append((_coseno(pregunta_emb, emb), datos["nombre"], archivo, chunk))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    top = candidatos[:top_k]

    contexto = "\n\n---\n\n".join(f"[Fuente: {nombre}]\n{chunk}" for _, nombre, _, chunk in top)
    prompt = (
        "Responde la pregunta del usuario ÚNICAMENTE usando el contexto de abajo, que son "
        "fragmentos de manuales técnicos. Si la respuesta no está en el contexto, dilo claramente "
        "en vez de inventar. Responde en español, de forma clara y concisa.\n\n"
        f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"
    )

    r = _ollama_post(
        "/api/chat",
        {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=420,
    )
    respuesta = r.get("message", {}).get("content", "(sin respuesta)")

    fuentes = [
        {"manual": nombre, "snippet": chunk[:220] + ("…" if len(chunk) > 220 else "")}
        for _, nombre, _, chunk in top
    ]
    return {"respuesta": respuesta, "fuentes": fuentes}


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RAG local sobre manuales convertidos")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index")
    p_idx.add_argument("-d", "--dir", default=RUTA_MANUALES_MD)

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("pregunta")
    p_ask.add_argument("-d", "--dir", default=RUTA_MANUALES_MD)
    p_ask.add_argument("-m", "--modelo", default=MODELO_CHAT_DEFAULT)

    args = parser.parse_args()
    if args.cmd == "index":
        indexar(args.dir)
    elif args.cmd == "ask":
        out = preguntar(args.pregunta, base_dir=args.dir, modelo=args.modelo)
        print("\n" + out["respuesta"] + "\n")
        print("Fuentes:")
        for f in out["fuentes"]:
            print(f"  - {f['manual']}: {f['snippet']}")
