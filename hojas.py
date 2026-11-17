# -*- coding: utf-8 -*-
"""
hojas.py — Fase 4. Material para mirar.

  hojas/por_anio_<anio>.png   todas las piezas de ese año, en grilla, rotuladas
  hojas/<startup>.png         la evolución de una startup, en orden cronológico
  paletas/por_anio.png        una tira por año con los colores dominantes (según medidas.csv)
  paletas/por_anio.csv        la misma información en tabla, con las piezas de origen

Cada celda muestra la primera pantalla de la página (los primeros 1440 x 900 px CSS de la
captura, es decir 2880 x 1800 px) reducida; no la página completa. Los rótulos llevan el año y
el nombre de la startup. Si una hoja ya existe y cambia, la anterior se guarda en historial/.

Uso:
    python hojas.py
"""

import csv
import io
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from estado import escribir
from versiones import guardar_bytes, guardar_texto

Image.MAX_IMAGE_PIXELS = None

AQUI = Path(__file__).resolve().parent
HOJAS = AQUI / "hojas"
PALETAS = AQUI / "paletas"
MINIATURAS = HOJAS / "_miniaturas"
CELDA_W, CELDA_H, ROTULO_H, MARGEN = 360, 225, 30, 10
PANTALLA = (2880, 1800)  # primera pantalla de la captura (viewport 1440x900 a escala 2)
FONDO, TEXTO, CELDA_FONDO = (245, 244, 240), (30, 30, 28), (222, 220, 214)


def fuente(tam=15):
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def limpiar(nombre):
    s = re.sub(r"[^\w\-. ]", "_", nombre).strip().replace(" ", "_")
    return s[:60] or "sin_nombre"


def leer(nombre):
    ruta = AQUI / nombre
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def tiene_pieza(pieza):
    """La pieza sirve para las hojas si existe la captura o su miniatura (las capturas pueden haberse movido fuera de la carpeta local)."""
    cache = MINIATURAS / f"{limpiar(pieza['startup'])}_{pieza['anio']}_{pieza['timestamp']}.png"
    return cache.exists() or (AQUI / pieza["archivo"]).exists()


def miniatura(pieza):
    """Primera pantalla reducida; se guarda en caché para no reabrir imágenes enormes."""
    ruta = AQUI / pieza["archivo"]
    cache = MINIATURAS / f"{limpiar(pieza['startup'])}_{pieza['anio']}_{pieza['timestamp']}.png"
    if cache.exists():
        return Image.open(cache).convert("RGB")
    im = Image.open(ruta).convert("RGB")
    recorte = im.crop((0, 0, min(im.width, PANTALLA[0]), min(im.height, PANTALLA[1])))
    recorte.thumbnail((CELDA_W, CELDA_H), Image.LANCZOS)
    MINIATURAS.mkdir(parents=True, exist_ok=True)
    recorte.save(cache)
    return recorte


def grilla(piezas, columnas, rotulo):
    f = fuente(15)
    filas = -(-len(piezas) // columnas)
    ancho = MARGEN + columnas * (CELDA_W + MARGEN)
    alto = MARGEN + filas * (CELDA_H + ROTULO_H + MARGEN)
    lienzo = Image.new("RGB", (ancho, alto), FONDO)
    d = ImageDraw.Draw(lienzo)
    for i, p in enumerate(piezas):
        x = MARGEN + (i % columnas) * (CELDA_W + MARGEN)
        y = MARGEN + (i // columnas) * (CELDA_H + ROTULO_H + MARGEN)
        d.rectangle((x, y, x + CELDA_W, y + CELDA_H), fill=CELDA_FONDO)
        mini = miniatura(p)
        lienzo.paste(mini, (x + (CELDA_W - mini.width) // 2, y))
        d.text((x + 2, y + CELDA_H + 5), rotulo(p), fill=TEXTO, font=f)
    return lienzo


def a_png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def cubeta(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return (r >> 4, g >> 4, b >> 4), (r, g, b)


def paletas(medidas):
    por_anio = defaultdict(list)
    for m in medidas:
        por_anio[m["anio"]].append(m)
    anios = sorted(por_anio)
    filas_csv, tiras = [], []
    for a in anios:
        piezas = por_anio[a]
        acum = defaultdict(lambda: [0.0, [0.0, 0.0, 0.0]])
        for m in piezas:
            for n in range(1, 6):
                hx, pc = m[f"color_{n}_hex"], m[f"color_{n}_pct"]
                if not hx.startswith("#"):
                    continue
                w = float(pc) / 100
                cub, rgb = cubeta(hx)
                acum[cub][0] += w
                for i in range(3):
                    acum[cub][1][i] += rgb[i] * w
        top = sorted(acum.items(), key=lambda x: -x[1][0])[:10]
        total = sum(v[0] for _, v in top) or 1
        colores = []
        for rank, (cub, (w, s)) in enumerate(top, 1):
            rgb = tuple(int(round(s[i] / w)) for i in range(3))
            hx = "#%02x%02x%02x" % rgb
            colores.append((hx, rgb, w / total))
            filas_csv.append((a, len(piezas), rank, hx, f"{100 * w / total:.2f}",
                              "; ".join(f"{m['startup']}:{m['timestamp']}" for m in piezas),
                              " | ".join(m["url_archivo"] for m in piezas)))
        tiras.append((a, len(piezas), colores))
    # Imagen: una tira por año
    f, f2 = fuente(16), fuente(12)
    W, H, ETQ = 900, 40, 130
    lienzo = Image.new("RGB", (ETQ + W + 2 * MARGEN, MARGEN + len(tiras) * (H + 26) + MARGEN), FONDO)
    d = ImageDraw.Draw(lienzo)
    for i, (a, n, colores) in enumerate(tiras):
        y = MARGEN + i * (H + 26)
        d.text((MARGEN, y + 8), f"{a}  (n={n})", fill=TEXTO, font=f)
        x = MARGEN + ETQ
        for hx, rgb, frac in colores:
            w = max(1, round(W * frac))
            d.rectangle((x, y, x + w, y + H), fill=rgb)
            x += w
        d.text((MARGEN + ETQ, y + H + 3), " ".join(c[0] for c in colores[:6]), fill=TEXTO, font=f2)
    return a_png(lienzo), filas_csv


def main():
    piezas = leer("indice.csv")
    medidas = leer("medidas.csv")
    if not piezas:
        print("No hay piezas en indice.csv")
        return
    por_anio, por_startup = defaultdict(list), defaultdict(list)
    for p in piezas:
        if tiene_pieza(p):
            por_anio[p["anio"]].append(p)
            por_startup[p["startup"]].append(p)
    total = len(por_anio) + len(por_startup) + 1
    hecho = 0
    cambios = 0
    for a in sorted(por_anio):
        lista = sorted(por_anio[a], key=lambda p: (p["startup"].lower(), p["timestamp"]))
        im = grilla(lista, 5, lambda p: f"{p['anio']} · {p['startup'][:34]}")
        cambios += guardar_bytes(HOJAS / f"por_anio_{a}.png", a_png(im))
        hecho += 1
        escribir("Hojas de contacto (Fase 4)", f"año {a}", hecho, total)
    for s in sorted(por_startup):
        lista = sorted(por_startup[s], key=lambda p: p["timestamp"])
        im = grilla(lista, min(4, max(1, len(lista))), lambda p: f"{p['anio']}")
        cambios += guardar_bytes(HOJAS / f"{limpiar(s)}.png", a_png(im))
        hecho += 1
        escribir("Hojas de contacto (Fase 4)", s, hecho, total)
    if medidas:
        png, filas = paletas(medidas)
        cambios += guardar_bytes(PALETAS / "por_anio.png", png)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["anio", "n_piezas", "posicion", "hex", "peso_pct", "piezas_startup_timestamp", "urls_snapshot"])
        w.writerows(filas)
        guardar_texto(PALETAS / "por_anio.csv", buf.getvalue())
        guardar_texto(PALETAS / "LEEME.md", """# Paletas por año

Fuente: `medidas.csv` (cinco colores dominantes por pieza, ver `medidas-metodo.md`).
Para cada año se suman los porcentajes de superficie de los colores de todas sus piezas, agrupando
colores en cubetas de 4 bits por canal; cada pieza pesa igual. Se muestran las 10 cubetas con más
peso, con el color promedio de la cubeta y su peso relativo entre esas 10. La tira no incluye el
resto de los colores de las piezas. `por_anio.csv` lista las piezas y URLs de cada año.
""")
    guardar_texto(HOJAS / "LEEME.md", """# Hojas de contacto

Cada celda es la primera pantalla de la captura (primeros 2880 x 1800 px de la imagen, equivalentes a
1440 x 900 px CSS), reducida a 360 px de ancho. No muestra la página completa. Las piezas están
ordenadas por nombre de startup (hojas por año) o cronológicamente (hojas por startup). Para ver
la pieza entera, abrir la imagen de `capturas/` indicada en `indice.csv`.
""")
    escribir("Hojas y paletas al día", f"{cambios} imágenes nuevas o cambiadas", total, total, situacion="terminado")
    print(f"{len(por_anio)} hojas por año, {len(por_startup)} por startup, paletas listas. Cambios: {cambios}")


if __name__ == "__main__":
    main()
