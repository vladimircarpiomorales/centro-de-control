"""
Guarda una página real de cada portal en tests/muestras/ para que las pruebas de
los lectores funcionen sin internet. Volver a ejecutarlo cuando un portal cambie
(y el lector se haya arreglado):  venv/bin/python tests/actualizar_muestras.py
"""
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from becas import _http_get

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "muestras")
MUESTRAS = {
    "infojobs.html": "https://www.infojobs.net/jobsearch/search-results/list.xhtml?"
                     + urllib.parse.urlencode({"keyword": "administrador de sistemas", "provinceIds": "33",
                                               "sinceDate": "_15_DAYS", "sortBy": "PUBLICATION_DATE"}),
    "tecnoempleo.html": "https://www.tecnoempleo.com/ofertas-trabajo/?"
                        + urllib.parse.urlencode({"te": "administrador de sistemas", "pr": ",263,"}),
    "linkedin.html": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                     + urllib.parse.urlencode({"keywords": "administrador de sistemas",
                                               "location": "Madrid, Community of Madrid, Spain",
                                               "f_TPR": "r604800", "start": "0"}),
    "telegram.html": "https://t.me/s/udemy_free_coupon",
    "reddit.xml": "https://www.reddit.com/r/udemyfreebies/new/.rss",
}

if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    for nombre, url in MUESTRAS.items():
        try:
            texto = _http_get(url, timeout=20)
            if nombre == "infojobs.html" and 'id="job-title-' not in texto:
                print(f"✗ {nombre}: InfoJobs ha servido un captcha; se conserva la muestra anterior")
                continue
            with open(os.path.join(DIR, nombre), "w", encoding="utf-8") as f:
                f.write(texto)
            print(f"✓ {nombre}: {len(texto) // 1024} KB")
        except Exception as e:
            print(f"✗ {nombre}: {e}")
        time.sleep(8)
