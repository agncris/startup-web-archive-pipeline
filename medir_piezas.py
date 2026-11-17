# -*- coding: utf-8 -*-
"""
medir_piezas.py — Fase 2. Medidas formales objetivas de cada captura de indice.csv.

Escribe medidas.csv agregando una fila por pieza (clave: archivo). No re-mide lo ya medido y
no sobrescribe nada. El método de cada medida está en medidas-metodo.md.

Uso:
    python medir_piezas.py
"""

import csv
import gzip
import json
import time
from pathlib import Path

import numpy as np
from bs4 import BeautifulSoup
from PIL import Image

from estado import escribir

Image.MAX_IMAGE_PIXELS = None

AQUI = Path(__file__).resolve().parent
INDICE = AQUI / "indice.csv"
SALIDA = AQUI / "medidas.csv"
VERSION_METODO = "1"
ESCALA = 2  # device_scale_factor de la captura
ND = "no disponible"
FRANJA = 400  # filas de píxeles procesadas por vez (memoria acotada)

CAMPOS = (["startup", "anio", "timestamp", "url_archivo", "archivo",
           "ancho_px", "alto_px", "ancho_css_px", "alto_pagina_css_px"]
          + [f"color_{i}_{c}" for i in range(1, 6) for c in ("hex", "pct")]
          + ["n_colores_distintos", "n_imagenes_html", "n_formularios_html", "n_campos_formulario_html",
             "caracteres_visibles", "prop_texto_vs_imagen", "version_metodo", "fecha_medicion"])


def medir_imagen(ruta):
    im = Image.open(ruta).convert("RGB")
    ancho, alto = im.size
    bitmap = np.zeros(1 << 24, dtype=bool)            # colores exactos vistos
    cuenta = np.zeros(4096, dtype=np.int64)           # píxeles por cubeta de 4 bits/canal
    suma = np.zeros((3, 4096), dtype=np.float64)      # suma de R, G, B por cubeta
    for y in range(0, alto, FRANJA):
        a = np.asarray(im.crop((0, y, ancho, min(y + FRANJA, alto))), dtype=np.uint8).reshape(-1, 3)
        r, g, b = a[:, 0].astype(np.int32), a[:, 1].astype(np.int32), a[:, 2].astype(np.int32)
        bitmap[(r << 16) | (g << 8) | b] = True
        cub = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
        cuenta += np.bincount(cub, minlength=4096)
        for i, canal in enumerate((r, g, b)):
            suma[i] += np.bincount(cub, weights=canal, minlength=4096)
    total = int(cuenta.sum())
    orden = np.argsort(-cuenta, kind="stable")[:5]
    paleta = []
    for k in orden:
        if cuenta[k] == 0:
            paleta.append((ND, ND))
            continue
        rgb = [int(round(suma[i][k] / cuenta[k])) for i in range(3)]
        paleta.append(("#%02x%02x%02x" % tuple(rgb), f"{100 * cuenta[k] / total:.2f}"))
    return ancho, alto, paleta, int(bitmap.sum())


def medir_html(ruta_gz):
    """Cuenta etiquetas del HTML archivado crudo. Sin el HTML, 'no disponible'."""
    if not ruta_gz.exists():
        return ND, ND, ND
    with gzip.open(ruta_gz, "rb") as fh:
        sopa = BeautifulSoup(fh.read(), "html.parser")
    n_img = len(sopa.find_all("img"))
    forms = sopa.find_all("form")
    campos = 0
    for f in forms:
        for c in f.find_all(["input", "select", "textarea"]):
            if c.name == "input" and (c.get("type", "text") or "text").lower() in ("hidden", "submit", "button", "reset", "image"):
                continue
            campos += 1
    return n_img, len(forms), campos


def completar():
    """Completa en medidas.csv los datos que salen del HTML crudo o del texto y no estaban al medir.

    Solo reemplaza celdas que dicen 'no disponible' y ahora sí se pueden calcular. La versión
    anterior de medidas.csv queda en historial/ (nada se pierde).
    """
    import io
    from versiones import guardar_texto
    with open(SALIDA, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    cambios = 0
    for r in filas:
        carpeta = Path(r["archivo"]).parent.name
        nombre = f"{r['anio']}_{r['timestamp']}"
        crudo = AQUI / "html_crudo" / carpeta / f"{nombre}.html.gz"
        if any(r[c] == ND for c in ("n_imagenes_html", "n_formularios_html", "n_campos_formulario_html")) and crudo.exists():
            r["n_imagenes_html"], r["n_formularios_html"], r["n_campos_formulario_html"] = medir_html(crudo)
            cambios += 1
        texto = AQUI / "texto" / carpeta / f"{nombre}.json"
        if r["caracteres_visibles"] == ND and texto.exists():
            r["caracteres_visibles"] = json.loads(texto.read_text(encoding="utf-8")).get("n_caracteres_visibles", ND)
            cambios += 1
    if cambios:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CAMPOS, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
        guardar_texto(SALIDA, buf.getvalue())
    print(f"completar: {cambios} celdas completadas en {SALIDA.name}")


def main():
    with open(INDICE, newline="", encoding="utf-8") as fh:
        piezas = list(csv.DictReader(fh))
    hechas = set()
    if SALIDA.exists():
        with open(SALIDA, newline="", encoding="utf-8") as fh:
            hechas = {r["archivo"] for r in csv.DictReader(fh)}
    pendientes = [p for p in piezas if p["archivo"] not in hechas]
    nuevo = not SALIDA.exists()
    total = len(pendientes)
    print(f"{len(piezas)} piezas indexadas, {len(hechas)} ya medidas, {total} por medir")
    with open(SALIDA, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        for i, p in enumerate(pendientes, 1):
            ruta = AQUI / p["archivo"]
            if not ruta.exists():
                print(f"  falta el archivo: {p['archivo']}")
                continue
            escribir("Midiendo piezas (Fase 2)", f"{p['startup']}, {p['anio']}", i - 1, total)
            ancho, alto, paleta, n_colores = medir_imagen(ruta)
            nombre = f"{p['anio']}_{p['timestamp']}"
            carpeta = Path(p["archivo"]).parent.name
            n_img, n_forms, n_campos = medir_html(AQUI / "html_crudo" / carpeta / f"{nombre}.html.gz")
            texto = AQUI / "texto" / carpeta / f"{nombre}.json"
            visibles = json.loads(texto.read_text(encoding="utf-8")).get("n_caracteres_visibles", ND) if texto.exists() else ND
            fila = {"startup": p["startup"], "anio": p["anio"], "timestamp": p["timestamp"],
                    "url_archivo": p["url_archivo"], "archivo": p["archivo"],
                    "ancho_px": ancho, "alto_px": alto, "ancho_css_px": ancho // ESCALA,
                    "alto_pagina_css_px": alto // ESCALA}
            for n, (hx, pc) in enumerate(paleta, 1):
                fila[f"color_{n}_hex"], fila[f"color_{n}_pct"] = hx, pc
            fila.update({"n_colores_distintos": n_colores, "n_imagenes_html": n_img,
                         "n_formularios_html": n_forms, "n_campos_formulario_html": n_campos,
                         "caracteres_visibles": visibles, "prop_texto_vs_imagen": ND,
                         "version_metodo": VERSION_METODO,
                         "fecha_medicion": time.strftime("%Y-%m-%d %H:%M:%S")})
            w.writerow(fila)
            fh.flush()
            print(f"  ok {p['startup']} {p['anio']}: {ancho}x{alto}, {n_colores} colores")
    escribir("Medidas al día", f"{total} piezas nuevas", total, total, situacion="terminado")
    print("Listo.")


if __name__ == "__main__":
    import sys
    if "--completar" in sys.argv:
        completar()
    else:
        main()
