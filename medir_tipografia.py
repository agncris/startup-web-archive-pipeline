# -*- coding: utf-8 -*-
"""
medir_tipografia.py: grupo tipográfico declarado en el HTML archivado de cada captura.

Ubica la tipografía declarada en grandes grupos históricos (romana, didona, egipcia, geométrica, grotesca).
Aquí solo se mide lo que el HTML declara; no se interpreta.

Qué mide: nombres de familia en `font-family` de <style> y style="...", y familias pedidas a Google Fonts o
Typekit. No ve los CSS externos (no se archivan en html_crudo), así que muchas piezas quedan sin dato. La
"fuente principal" es la familia más declarada, no necesariamente la del texto del cuerpo.

Los grupos son una tabla editable (abajo). Los cinco primeros son los grupos históricos clásicos; "humanista",
"monoespaciada" y "display o manuscrita" se agregan porque muchas familias comunes no caben en los cinco.
Una familia que no está en la tabla queda "sin clasificar" y se lista en el resumen para su revisión.

Escribe tipografias.csv (una fila por pieza, no re-mide lo medido, no sobrescribe) y
reportes/tipografia_AAAAMMDD_HHMMSS.md con el resumen por año.

Uso:
    python medir_tipografia.py
"""
import csv
import gzip
import re
import sys
import time
from urllib.parse import unquote
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

csv.field_size_limit(sys.maxsize)
AQUI = Path(__file__).resolve().parent
INDICE = AQUI / "indice.csv"
SALIDA = AQUI / "tipografias.csv"
VERSION_METODO = "3"
ND = "no disponible"
CAMPOS = ["startup", "anio", "timestamp", "archivo", "fuentes_declaradas", "fuente_principal", "grupo", "origen",
          "version_metodo", "fecha_medicion"]

# Grupos: se busca la primera regla cuyo texto esté contenido en el nombre normalizado (minúsculas, sin guiones).
GRUPOS = [
    ("didona", ["playfair", "bodoni", "didot", "abril fatface", "dm serif", "chonburi"]),
    ("egipcia", ["slab", "rockwell", "arvo", "bitter", "crete round", "museoslab", "clarendon", "zilla"]),
    ("romana", ["georgia", "times", "garamond", "baskerville", "merriweather", "lora", "ptserif", "pt serif", "crimson",
                "cormorant", "palatino", "book antiqua", "cambria", "libre caslon", "noto serif", "source serif",
                "spectral", "fahkwang", "droid serif", "bree serif"]),
    ("geométrica", ["montserrat", "poppins", "raleway", "nunito", "futura", "avenir", "century gothic", "josefin sans",
                    "quicksand", "comfortaa", "questrial", "varela", "urbanist", "outfit", "lexend", "dm sans",
                    "red hat", "manrope", "plus jakarta", "sora", "jost", "didact", "gotham", "proxima"]),
    ("grotesca", ["helvetica", "arial", "roboto", "inter", "rubik", "barlow", "space grotesk", "oswald", "asap",
                  "dinnext", "din next", "akzidenz", "univers", "franklin", "work sans", "karla", "public sans",
                  "ibm plex sans", "heebo", "archivo", "overpass", "sf pro", "system-ui", "-apple-system", "segoe",
                  "arimo", "liberation sans", "bebas", "anton", "pt sans narrow", "mukta"]),
    ("humanista", ["open sans", "lato", "source sans", "ptsans", "pt sans", "hind", "droid sans", "signika", "verdana",
                   "tahoma", "trebuchet", "fira sans", "noto sans", "ubuntu", "cabin", "catamaran", "myriad", "calibri",
                   "candara", "gill sans", "lucida", "muli", "mulish", "titillium", "exo", "maven", "istok", "oxygen"]),
    ("monoespaciada", ["monospace", "consolas", "menlo", "monaco", "courier", "source code", "fira code", "roboto mono",
                       "space mono", "jetbrains", "ibm plex mono", "inconsolata"]),
    ("display o manuscrita", ["pacifico", "lobster", "dancing script", "satisfy", "caveat", "great vibes", "indie flower",
                              "shadows into light", "permanent marker", "amatic", "righteous", "fredoka", "baloo",
                              "comic", "cursive", "fantasy", "bangers", "press start"]),
]
GENERICAS = {"sans serif", "sans-serif", "serif", "inherit", "initial", "unset", "default", "system-ui", "-apple-system",
             "blinkmacsystemfont", "apple system", "ui monospace", "monospace", "cursive", "fantasy", "arial"}  # arial queda como grotesca si es la única
IGNORAR = re.compile(r"(icon|awesome|glyph|etmodules|dashicons|genericons|material|symbols|wfont|^var\(|^var$|^\s*$|astra|snippet|"
                     r"!important$|^\d|^\.|webfont$|fontello|ionicons|linearicons|elusive|themify)", re.IGNORECASE)
RE_FF = re.compile(r"font-family\s*:\s*([^;}{]+)", re.IGNORECASE)
RE_GOOGLE = re.compile(r"fonts\.googleapis\.com/css2?\?family=([^\"'&>\s]+)", re.IGNORECASE)
RE_TYPEKIT = re.compile(r"font-family\s*:\s*[\"']?([a-z0-9 \-]+)[\"']?\s*,", re.IGNORECASE)


def limpiar(nombre):
    n = nombre.replace("&quot;", "").replace("&quot", "").replace("&#39;", "").replace("\\", "")
    n = re.split(r"[\"'<>]\s*[>/<a-z]", n)[0] if re.search(r"[<>]", n) else n
    n = re.sub(r"!important", "", n, flags=re.IGNORECASE)
    n = n.strip(" \t\r\n\"'").lower()
    n = re.sub(r"[-_]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def grupo_de(nombre):
    n = limpiar(nombre)
    for g, claves in GRUPOS:
        for c in claves:
            if c in n or c.replace(" ", "") in n.replace(" ", ""):
                return g
    return "sin clasificar"


def familias(html):
    """Devuelve (Counter de familias, origen). Cada declaración cuenta su primera familia con nombre."""
    c = Counter()
    origen = set()
    for m in RE_GOOGLE.finditer(html):
        origen.add("google")
        for fam in re.split(r"\|", unquote(m.group(1))):
            fam = re.sub(r"[:@;].*", "", fam.replace("+", " ").replace("%20", " "))
            fam = limpiar(fam)
            if fam and not IGNORAR.search(fam):
                c[fam] += 2     # pedir una familia a Google Fonts pesa un poco más que una mención suelta
    for m in RE_FF.finditer(html):
        origen.add("css")
        lista = [limpiar(x) for x in m.group(1).split(",")]
        for x in lista:
            if not x or IGNORAR.search(x):
                continue
            if x in GENERICAS and x != "arial":
                continue
            c[x] += 1
            break
    return c, origen


def medir(ruta):
    with gzip.open(ruta, "rb") as fh:
        html = fh.read().decode("utf-8", "ignore")
    c, origen = familias(html)
    if not c:
        return ND, ND, "sin dato", "+".join(sorted(origen)) or "ninguno"
    top = c.most_common(5)
    principal = top[0][0]
    return " | ".join(f"{n} ({k})" for n, k in top), principal, grupo_de(principal), "+".join(sorted(origen))


def main():
    with open(INDICE, newline="", encoding="utf-8") as fh:
        piezas = list(csv.DictReader(fh))
    hechas = set()
    if SALIDA.exists():
        with open(SALIDA, newline="", encoding="utf-8") as fh:
            hechas = {r["archivo"] for r in csv.DictReader(fh)}
    pendientes = [p for p in piezas if p["archivo"] not in hechas]
    nuevo = not SALIDA.exists()
    print(f"{len(piezas)} piezas indexadas, {len(hechas)} ya medidas, {len(pendientes)} por medir")
    with open(SALIDA, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, lineterminator="\n")
        if nuevo:
            w.writeheader()
        for i, p in enumerate(pendientes, 1):
            carpeta = Path(p["archivo"]).parent.name
            crudo = AQUI / "html_crudo" / carpeta / f"{p['anio']}_{p['timestamp']}.html.gz"
            if crudo.exists():
                try:
                    decl, principal, grupo, origen = medir(crudo)
                except (OSError, EOFError):
                    decl, principal, grupo, origen = ND, ND, "sin dato", "html ilegible"
            else:
                decl, principal, grupo, origen = ND, ND, "sin dato", "sin html crudo"
            w.writerow({"startup": p["startup"], "anio": p["anio"], "timestamp": p["timestamp"], "archivo": p["archivo"],
                        "fuentes_declaradas": decl, "fuente_principal": principal, "grupo": grupo, "origen": origen,
                        "version_metodo": VERSION_METODO, "fecha_medicion": time.strftime("%Y-%m-%d %H:%M:%S")})
            if i % 500 == 0:
                fh.flush()
                print(f"  {i}/{len(pendientes)}")
    resumen()


def resumen():
    with open(SALIDA, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    por_anio = defaultdict(list)
    for r in filas:
        por_anio[int(r["anio"])].append(r)
    anios = sorted(por_anio)
    grupos = [g for g, _ in GRUPOS] + ["sin clasificar"]
    L = [f"# Grupo tipográfico declarado en el HTML ({datetime.now():%Y-%m-%d %H:%M})\n",
         f"{len(filas)} piezas en `tipografias.csv`. Método y límites en la cabecera de `medir_tipografia.py`. "
         "La tabla de grupos es editable en el script; los cinco primeros son los grupos históricos clásicos y "
         "humanista, monoespaciada y display se agregan aparte. El HTML no incluye los CSS externos, "
         "así que la cobertura es parcial y sesgada hacia sitios con CSS en línea o Google Fonts.\n",
         "## 1. Cobertura por año\n",
         "| año | piezas | con familia declarada | % |",
         "|---|---|---|---|"]
    for a in anios:
        ps = por_anio[a]
        con = [r for r in ps if r["grupo"] != "sin dato"]
        L.append(f"| {a} | {len(ps)} | {len(con)} | {100 * len(con) / len(ps):.0f} |")
    L += ["\n## 2. Grupo de la fuente principal (% de las piezas con familia declarada)\n",
          "| año | n | " + " | ".join(grupos) + " |", "|---|---|" + "---|" * len(grupos)]
    for a in anios:
        con = [r for r in por_anio[a] if r["grupo"] != "sin dato"]
        if not con:
            L.append(f"| {a} | 0 | " + " | ".join(["[n]"] * len(grupos)) + " |")
            continue
        c = Counter(r["grupo"] for r in con)
        L.append(f"| {a} | {len(con)} | " + " | ".join(f"{100 * c[g] / len(con):.0f}" for g in grupos) + " |")
    L += ["\n## 3. Familias más comunes por grupo (para revisar la tabla)\n"]
    fam = defaultdict(Counter)
    for r in filas:
        if r["grupo"] != "sin dato":
            fam[r["grupo"]][r["fuente_principal"]] += 1
    for g in grupos:
        if fam[g]:
            L.append(f"- **{g}**: " + ", ".join(f"{n} ({k})" for n, k in fam[g].most_common(12)))
    sc = fam["sin clasificar"]
    L.append(f"\nFamilias sin clasificar: {len(sc)} distintas. Las 40 más frecuentes, para decidir si entran a la tabla:\n")
    L.append(", ".join(f"{n} ({k})" for n, k in sc.most_common(40)) or "[n]")
    salida = AQUI / "reportes" / f"tipografia_{datetime.now():%Y%m%d_%H%M%S}.md"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(salida)


if __name__ == "__main__":
    main()
