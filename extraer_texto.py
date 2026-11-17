# -*- coding: utf-8 -*-
"""
extraer_texto.py — Fase 1. Baja el HTML archivado de cada pieza de indice.csv (sin
re-renderizar) y guarda un JSON por pieza en texto/<startup>/<anio>_<timestamp>.json.

Es reanudable: si el JSON ya existe no se vuelve a bajar. Nunca se sobrescribe nada.

Cada JSON lleva:
  startup, anio, timestamp, url_archivo (la de indice.csv), url_html_crudo (la que se pidió),
  url_final (a donde terminó la petición tras redirecciones), fecha_extraccion, metodo.
Un dato ausente se escribe "no disponible" (texto) o [] (listas sin elementos hallados).

Uso:
    python extraer_texto.py
"""

import csv
import gzip
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from estado import escribir

AQUI = Path(__file__).resolve().parent
INDICE = AQUI / "indice.csv"
SALIDA = AQUI / "texto"
CRUDO = AQUI / "html_crudo"  # copia comprimida del HTML tal como lo devolvió el archivo web
UA = {"User-Agent": "Mozilla/5.0 (academic research; doctoral thesis)"}
ND = "no disponible"
VERSION_METODO = "1"

METODO = {
    "version": VERSION_METODO,
    "fuente": "HTML archivado crudo (URL con sufijo id_, sin reescritura del archivo web)",
    "title": "contenido de la primera etiqueta <title>",
    "meta_description": "atributo content de <meta name=description>",
    "encabezados": "etiquetas h1 y h2 en el orden del documento",
    "botones": "texto de <button>, value de <input type=submit|button|reset>, "
               "y de <a role=button>",
    "enlaces_de_accion": "<a> cuya clase contiene btn, button o cta; se da texto y href",
    "imagenes": "cada <img>: src y atributo alt (vacío si no tiene)",
    "texto_visible": "texto del documento sin script, style, noscript, template ni head; "
                     "espacios colapsados, un bloque por línea",
}


def separar(url_archivo):
    m = re.match(r"https://web\.archive\.org/web/(\d{14})/(.+)$", url_archivo)
    if not m:
        raise ValueError(f"URL de archivo con formato inesperado: {url_archivo}")
    return m.group(1), m.group(2)


ILEGIBLES = ("got more than 100 headers",)   # fallos definitivos de la respuesta archivada, no de la conexión


def bajar(url, intentos=4):
    """Devuelve (respuesta, error). Ante conexión rechazada espera de verdad y reintenta."""
    err = None
    for n in range(intentos + 2):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            return r, None
        except requests.exceptions.ConnectionError as e:
            err = f"{type(e).__name__}: {e}"
            # Hay respuestas archivadas que la biblioteca no puede leer (más de 100 cabeceras). Llegan como error de
            # conexión, pero el archivo sí responde: esperar no las arregla. Antes cada una costaba 31 minutos por lote.
            if any(m in err for m in ILEGIBLES):
                return None, err
            espera = 90 * (n + 1)
            escribir("Esperando que el archivo web acepte conexiones", f"reintento en {espera} s",
                     situacion="pausado")
            time.sleep(espera)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if n >= intentos - 1:
                break
            time.sleep(4 * (n + 1))
    return None, err


def limpiar(s):
    return re.sub(r"\s+", " ", s or "").strip()


def extraer(contenido):
    sopa = BeautifulSoup(contenido, "html.parser")

    def uno(valor):
        valor = limpiar(valor)
        return valor if valor else ND

    titulo = sopa.find("title")
    meta = sopa.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    html_tag = sopa.find("html")

    encabezados = [{"nivel": t.name, "texto": limpiar(t.get_text(" "))}
                   for t in sopa.find_all(["h1", "h2"]) if limpiar(t.get_text(" "))]

    botones = []
    for t in sopa.find_all("button"):
        if limpiar(t.get_text(" ")):
            botones.append(limpiar(t.get_text(" ")))
    for t in sopa.find_all("input", attrs={"type": re.compile(r"^(submit|button|reset)$", re.I)}):
        if limpiar(t.get("value", "")):
            botones.append(limpiar(t.get("value")))
    for t in sopa.find_all("a", attrs={"role": re.compile(r"^button$", re.I)}):
        if limpiar(t.get_text(" ")):
            botones.append(limpiar(t.get_text(" ")))

    acciones = []
    for t in sopa.find_all("a", class_=re.compile(r"(^|[\s_-])(btn|button|cta)([\s_-]|$)", re.I)):
        texto = limpiar(t.get_text(" "))
        if texto or t.get("href"):
            acciones.append({"texto": texto or ND, "href": t.get("href", ND)})

    imagenes = [{"src": i.get("src", ND), "alt": limpiar(i.get("alt", ""))}
                for i in sopa.find_all("img")]

    # Texto visible: se trabaja sobre una copia para no alterar lo ya extraído.
    cuerpo = BeautifulSoup(contenido, "html.parser")
    for t in cuerpo(["script", "style", "noscript", "template", "head"]):
        t.decompose()
    bloques = [limpiar(b) for b in cuerpo.get_text("\n").splitlines()]
    visible = "\n".join(b for b in bloques if b)

    return {
        "idioma_declarado": uno(html_tag.get("lang", "") if html_tag else ""),
        "title": uno(titulo.get_text(" ") if titulo else ""),
        "meta_description": uno(meta.get("content", "") if meta else ""),
        "encabezados": encabezados,
        "botones": botones,
        "enlaces_de_accion": acciones,
        "imagenes": imagenes,
        "n_imagenes": len(imagenes),
        "texto_visible": visible if visible else ND,
        "n_caracteres_visibles": len(visible),
    }


SIN_HTML = Path(__file__).resolve().parent / "texto_sin_html.csv"   # piezas cuyo HTML crudo el archivo web negó de forma definitiva (403 o 404)


def cargar_sin_html():
    if not SIN_HTML.exists():
        return set()
    with open(SIN_HTML, newline="", encoding="utf-8") as fh:
        return {r["timestamp"] + "|" + r["startup"] for r in csv.DictReader(fh)}


def anotar_sin_html(p, err):
    """403 y 404 son respuestas definitivas del archivo: se anotan para no volver a pedirlas en cada lote. Nada se borra: es un registro aparte."""
    nuevo = not SIN_HTML.exists()
    with open(SIN_HTML, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["startup", "anio", "timestamp", "error", "fecha"])
        w.writerow([p["startup"], p["anio"], p["timestamp"], str(err)[:160], time.strftime("%Y-%m-%d %H:%M:%S")])


def main():
    if not INDICE.exists():
        sys.exit("Falta indice.csv")
    with open(INDICE, newline="", encoding="utf-8") as fh:
        piezas = list(csv.DictReader(fh))

    total = len(piezas)
    nuevas = fallos = 0
    sin_html = cargar_sin_html()
    escribir("Bajando el texto (HTML archivado) de cada pieza", hecho=0, total=total)
    for i, p in enumerate(piezas, 1):
        carpeta = SALIDA / Path(p["archivo"]).parent.name
        destino = carpeta / f"{p['anio']}_{p['timestamp']}.json"
        crudo = CRUDO / Path(p["archivo"]).parent.name / f"{p['anio']}_{p['timestamp']}.html.gz"
        if destino.exists() and crudo.exists():
            continue
        if p["timestamp"] + "|" + p["startup"] in sin_html and not destino.exists():
            continue   # ya se sabe que el archivo no entrega su HTML (403 o 404); ver texto_sin_html.csv
        ts, original = separar(p["url_archivo"])
        url_crudo = f"https://web.archive.org/web/{ts}id_/{original}"
        escribir("Bajando el texto (HTML archivado) de cada pieza", f"{p['startup']}, {p['anio']}", i - 1, total)
        r, err = bajar(url_crudo)
        if err:
            fallos += 1
            print(f"  FALLÓ {p['startup']} {p['anio']}: {err}")
            if re.search(r"\b(403|404)\b", str(err)) or any(m in str(err) for m in ILEGIBLES):
                anotar_sin_html(p, err)
                sin_html.add(p["timestamp"] + "|" + p["startup"])
            continue
        if not crudo.exists():
            crudo.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(crudo, "wb") as fh:
                fh.write(r.content)
        if destino.exists():
            time.sleep(3)  # el JSON ya estaba: solo faltaba guardar el HTML crudo
            continue
        datos = {
            "startup": p["startup"],
            "anio": p["anio"],
            "timestamp": p["timestamp"],
            "url_archivo": p["url_archivo"],
            "url_html_crudo": url_crudo,
            "url_final": r.url,
            "http_estado": r.status_code,
            "tamano_html_bytes": len(r.content),
            "fecha_extraccion": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metodo": METODO,
        }
        datos.update(extraer(r.content))
        carpeta.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        nuevas += 1
        print(f"  ok {p['startup']} {p['anio']}: {datos['n_caracteres_visibles']} caracteres")
        time.sleep(3)

    escribir("Texto recolectado", f"{nuevas} nuevos, {fallos} fallos", total, total, situacion="terminado")
    print(f"\n{nuevas} JSON nuevos, {fallos} fallos. Carpeta: {SALIDA.name}/")


if __name__ == "__main__":
    main()
