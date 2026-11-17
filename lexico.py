# -*- coding: utf-8 -*-
"""
lexico.py — Fase 3. Corpus léxico a partir del texto de la Fase 1 (texto/*/*.json).

Salidas en lexico/ (tablas, sin interpretación):
  frecuencias.csv   término por pieza (startup y año)
  series.csv        frecuencia de cada término por año
  compartidos.csv   términos presentes en más de una startup el mismo año
  coocurrencias.csv pares de términos que aparecen juntos en una misma pieza
  stopwords.txt     lista de palabras vacías usada (para citarla)

Cada fila de frecuencias.csv lleva timestamp y URL del snapshot. En las tablas agregadas
las piezas de origen se listan como startup:timestamp y sus URLs.

Si una salida ya existe y cambia, la anterior se guarda en lexico/historial/.

Uso:
    python lexico.py
"""

import csv
import gzip
import io
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from estado import escribir
from versiones import guardar_bytes, guardar_texto

AQUI = Path(__file__).resolve().parent
TEXTO = AQUI / "texto"
SALIDA = AQUI / "lexico"
CAMPOS_TEXTO = ("title", "meta_description", "texto_visible")
MIN_LARGO = 3
MIN_PIEZAS_SERIE = 2        # un término entra en series.csv si aparece en al menos 2 piezas
MIN_DF_COOC = 5             # coocurrencias: términos presentes en al menos 5 piezas
MIN_JUNTOS_COOC = 5         # ...y pares que coinciden en al menos 5 piezas
ND = "no disponible"

STOP_ES = """a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el ella ellas
ello ellos en entre era erais eran eras eres es esa esas ese eso esos esta estaba estaban estado estamos estan estar
estas este esto estos estoy fue fueron fui fuimos ha habia han hasta hay la las le les lo los mas me mi mis mucho muchos
muy nada ni no nos nosotros nuestra nuestras nuestro nuestros o os otra otras otro otros para pero poco por porque que
quien quienes se sea sean ser si sido sin sobre sois solo somos son soy su sus tambien tanto te tenemos tener tengo ti
todo todos tu tus un una uno unas unos vosotros vuestra vuestro y ya yo"""
STOP_EN = """a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers herself him himself
his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours
ourselves out over own same she should so some such than that the their theirs them themselves then there these they this
those through to too under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves also can may get got one two via per"""
STOPWORDS = sorted(set(STOP_ES.split()) | set(STOP_EN.split()))
STOPSET = set(STOPWORDS)
RE_TOKEN = re.compile(r"[^\W\d_]{%d,}" % MIN_LARGO, re.UNICODE)


def tokenizar(texto):
    return [t for t in RE_TOKEN.findall(texto.lower()) if t not in STOPSET]


def cargar_piezas():
    piezas = []
    for ruta in sorted(TEXTO.glob("*/*.json")):
        d = json.loads(ruta.read_text(encoding="utf-8"))
        partes = [d.get(c, "") for c in CAMPOS_TEXTO if d.get(c, ND) != ND]
        tokens = tokenizar(" ".join(partes))
        piezas.append({"startup": d["startup"], "anio": d["anio"], "timestamp": d["timestamp"],
                       "url": d["url_archivo"], "tokens": tokens, "clave": f"{d['startup']}:{d['timestamp']}"})
    return piezas


def a_csv(cabecera, filas):
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cabecera)
    w.writerows(filas)
    return buf.getvalue()


def main():
    piezas = cargar_piezas()
    escribir("Calculando corpus léxico (Fase 3)", f"{len(piezas)} piezas con texto", 0, 4)
    if not piezas:
        print("No hay texto en texto/ todavía.")
        return

    frec_rows = []
    cont_pieza = []
    for p in piezas:
        c = Counter(p["tokens"])
        cont_pieza.append(c)
        n = len(p["tokens"])
        for t, f in sorted(c.items(), key=lambda x: (-x[1], x[0])):
            frec_rows.append((p["startup"], p["anio"], p["timestamp"], p["url"], t, f, n, f"{1000 * f / n:.3f}"))
    guardar_texto(SALIDA / "frecuencias.csv", a_csv(
        ["startup", "anio", "timestamp", "url_archivo", "termino", "frecuencia", "n_tokens_pieza", "frecuencia_por_mil"],
        frec_rows))

    # Series por año
    anios = sorted({p["anio"] for p in piezas})
    piezas_anio = Counter(p["anio"] for p in piezas)
    tokens_anio = Counter()
    for p in piezas:
        tokens_anio[p["anio"]] += len(p["tokens"])
    por_termino = defaultdict(lambda: defaultdict(lambda: [0, set(), set()]))  # termino -> anio -> [freq, startups, piezas]
    piezas_con = Counter()
    for p, c in zip(piezas, cont_pieza):
        for t, f in c.items():
            reg = por_termino[t][p["anio"]]
            reg[0] += f
            reg[1].add(p["startup"])
            reg[2].add(p["clave"])
            piezas_con[t] += 1
    series = []
    for t in sorted(por_termino):
        if piezas_con[t] < MIN_PIEZAS_SERIE:
            continue
        for a in anios:
            f, s, pz = por_termino[t][a] if a in por_termino[t] else (0, set(), set())
            series.append((t, a, f, len(pz), len(s), piezas_anio[a], tokens_anio[a],
                           f"{1000 * f / tokens_anio[a]:.3f}" if tokens_anio[a] else ND))
    guardar_texto(SALIDA / "series.csv", a_csv(
        ["termino", "anio", "frecuencia_total", "n_piezas_con_termino", "n_startups_con_termino",
         "n_piezas_del_anio", "n_tokens_del_anio", "frecuencia_por_mil_tokens"], series))
    escribir("Calculando corpus léxico (Fase 3)", "series listas", 1, 4)

    # Compartidos: mismo año, más de una startup
    url_de = {p["clave"]: p["url"] for p in piezas}
    comp = []
    for t, por_a in por_termino.items():
        for a, (f, startups, claves) in por_a.items():
            if len(startups) >= 2:
                cl = sorted(claves)
                comp.append((a, t, len(startups), f, "; ".join(sorted(startups)),
                             "; ".join(cl), " | ".join(url_de[c] for c in cl)))
    comp.sort(key=lambda r: (r[0], -r[2], -r[3], r[1]))
    guardar_texto(SALIDA / "compartidos.csv", a_csv(
        ["anio", "termino", "n_startups", "frecuencia_total", "startups", "piezas_startup_timestamp", "urls_snapshot"], comp))
    escribir("Calculando corpus léxico (Fase 3)", "compartidos listos", 2, 4)

    # Coocurrencias: pares en la misma pieza (presencia, no frecuencia)
    N = len(piezas)
    df = Counter()
    conjuntos = []
    for c in cont_pieza:
        s = set(c)
        conjuntos.append(s)
        df.update(s)
    candidatos = sorted(t for t, n in df.items() if n >= MIN_DF_COOC)
    cand = set(candidatos)
    # Cada pieza tiene un número (id_pieza); piezas.csv lo traduce a startup, timestamp y URL del snapshot.
    # Así la tabla de pares no repite las URLs (antes pesaba 275 MB) y la trazabilidad se mantiene.
    id_de = {p["clave"]: i for i, p in enumerate(piezas, 1)}
    guardar_texto(SALIDA / "piezas.csv", a_csv(
        ["id_pieza", "startup", "anio", "timestamp", "url_archivo"],
        [(i, p["startup"], p["anio"], p["timestamp"], p["url"]) for i, p in enumerate(piezas, 1)]))
    juntos = defaultdict(list)
    for p, s in zip(piezas, conjuntos):
        for a, b in combinations(sorted(s & cand), 2):
            juntos[(a, b)].append(id_de[p["clave"]])
    cooc, rastro = [], []
    for (a, b), ids in juntos.items():
        n = len(ids)
        if n < MIN_JUNTOS_COOC:
            continue
        pmi = math.log2((n / N) / ((df[a] / N) * (df[b] / N)))
        dice = 2 * n / (df[a] + df[b])
        cooc.append((a, b, n, df[a], df[b], N, f"{pmi:.3f}", f"{dice:.3f}"))
        rastro.append((a, b, " ".join(str(i) for i in sorted(ids))))
    orden = sorted(range(len(cooc)), key=lambda i: (-float(cooc[i][6]), -cooc[i][2], cooc[i][0], cooc[i][1]))
    cooc = [cooc[i] for i in orden]
    rastro = [rastro[i] for i in orden]
    guardar_texto(SALIDA / "coocurrencias.csv", a_csv(
        ["termino_a", "termino_b", "n_piezas_juntos", "n_piezas_a", "n_piezas_b", "n_piezas_total",
         "pmi", "dice"], cooc))
    # Piezas de cada par, comprimidas. mtime=0 para que el archivo sea idéntico si los datos no cambian.
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(a_csv(["termino_a", "termino_b", "ids_pieza"], rastro).encode("utf-8"))
    guardar_bytes(SALIDA / "coocurrencias_piezas.csv.gz", buf.getvalue())
    guardar_texto(SALIDA / "stopwords.txt", "\n".join(STOPWORDS) + "\n")
    guardar_texto(SALIDA / "LEEME.md", f"""# Corpus léxico: método

Fuente: `texto/*/*.json` (Fase 1). Campos usados: {", ".join(CAMPOS_TEXTO)}. {len(piezas)} piezas, años {anios[0]}-{anios[-1]}.

- **Tokenización:** minúsculas; secuencias de letras de {MIN_LARGO} o más caracteres (sin cifras ni guiones bajos).
- **Palabras vacías:** `stopwords.txt` (español e inglés; el corpus tiene páginas en ambos idiomas). No se hace lematización ni se unen
  formas de una misma palabra (p. ej. singular y plural cuentan por separado).
- **frecuencias.csv:** una fila por término y pieza. `frecuencia_por_mil` = frecuencia / tokens de la pieza × 1000.
- **series.csv:** por término y año; incluye años con frecuencia 0. Solo términos que aparecen en al menos {MIN_PIEZAS_SERIE} piezas.
  `frecuencia_por_mil_tokens` normaliza por el total de tokens de ese año (los años tienen cantidades de piezas distintas).
- **compartidos.csv:** términos que aparecen en piezas de 2 o más startups distintas el mismo año.
- **coocurrencias.csv:** pares de términos presentes en la misma pieza (presencia, no frecuencia). Solo términos en al menos
  {MIN_DF_COOC} piezas y pares que coinciden en al menos {MIN_JUNTOS_COOC} piezas. `pmi` = log2( P(a,b) / (P(a) P(b)) ) con P calculada
  sobre el total de piezas; `dice` = 2·n(a,b) / (n(a)+n(b)). Los umbrales son un criterio práctico de este script para acotar la tabla;
  las columnas permiten aplicar otros.
- **coocurrencias_piezas.csv.gz y piezas.csv (trazabilidad de cada par):** el `.gz` tiene, por cada par de `coocurrencias.csv`, la lista de
  `id_pieza` donde coinciden (mismo orden que la tabla; columnas `termino_a`, `termino_b`, `ids_pieza`). `piezas.csv` traduce cada
  `id_pieza` a startup, año, timestamp y URL completa del snapshot en el archivo web. Para leerlo:
  `gzip -dc lexico/coocurrencias_piezas.csv.gz`. Antes cada fila repetía las URLs y el archivo pesaba 275 MB.

Limitaciones: el texto incluye navegación, pie de página y avisos legales de cada sitio. El archivo web puede haber guardado
solo parte del texto de una página. Páginas con el mismo texto en años distintos cuentan cada año.
""")
    escribir("Corpus léxico al día", f"{len(piezas)} piezas, {len(cooc)} pares", 4, 4, situacion="terminado")
    print(f"{len(piezas)} piezas, {len(frec_rows)} filas de frecuencias, {len(series)} de series, "
          f"{len(comp)} compartidos, {len(cooc)} coocurrencias.")


if __name__ == "__main__":
    main()
