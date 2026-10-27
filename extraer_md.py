import json
import sys

# Comprobamos que nos hayas dado el nombre del archivo
if len(sys.argv) < 2:
    print("⚠️ Uso: python3 extraer_md.py tu_archivo.json")
    sys.exit()

archivo_json = sys.argv[1]
archivo_md = archivo_json.replace(".json", ".md")

try:
    # 1. Abrimos el archivo JSON que te dio el servidor
    with open(archivo_json, 'r', encoding='utf-8') as f:
        datos = json.load(f)

    # 2. Buscamos el contenido. (Dependiendo del servidor, puede llamarse 'markdown', 'text' o estar suelto)
    contenido = ""
    if isinstance(datos, dict):
        # Busca las claves más comunes
        contenido = datos.get('markdown', datos.get('text', str(datos)))
    else:
        contenido = str(datos)

    # 3. Lo guardamos como un archivo Markdown (.md)
    with open(archivo_md, 'w', encoding='utf-8') as f:
        f.write(contenido)

    print(f"✅ ¡Éxito! Tu archivo Markdown se ha guardado como: {archivo_md}")

except Exception as e:
    print(f"❌ Ocurrió un error: {e}")
