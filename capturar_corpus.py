# -*- coding: utf-8 -*-
"""
capturar_corpus.py — Reúne piezas históricas de sitios web desde el archivo web
(Wayback Machine) para el corpus de la tesis.

Uso:
    python capturar_corpus.py verificar     # consulta el índice CDX; no descarga nada
    python capturar_corpus.py capturar      # captura de pantalla de cada snapshot

Entrada:  dominios.csv   (startup, dominio, generacion, notas)
Salida:   cobertura.csv  (modo verificar)
          capturas/<startup>/<anio>_<timestamp>.png  e  indice.csv  (modo capturar)
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageStat

from collections import Counter

import ritmo_archivo
from estado import escribir

Image.MAX_IMAGE_PIXELS = None  # las portadas largas superan el límite por defecto

AQUI = Path(__file__).resolve().parent
ENTRADA = AQUI / "dominios.csv"
COBERTURA = AQUI / "cobertura.csv"
INDICE = AQUI / "indice.csv"
SALIDA = AQUI / "capturas"
CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "Mozilla/5.0 (academic research; doctoral thesis)"}
CAMPOS_INDICE = ["startup", "generacion", "anio", "timestamp", "url_archivo", "archivo"]

OCULTAR_BARRA = """
#wm-ipp-base, #wm-ipp, div[id^="wm-ipp"] { display:none !important; height:0 !important; }
body { margin-top: 0 !important; }
"""


def limpiar(nombre):
    s = re.sub(r"[^\w\-. ]", "_", nombre).strip().replace(" ", "_")
    return s[:60] or "sin_nombre"


def leer_dominios():
    if not ENTRADA.exists():
        sys.exit(f"Falta {ENTRADA.name}")
    filas = []
    with open(ENTRADA, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            dom = (r.get("dominio") or "").strip()
            if not dom:
                continue  # sin dominio confirmado: no se inventa
            r["dominio"] = re.sub(r"^https?://", "", dom).strip("/")
            filas.append(r)
    return filas


def variantes(dominio):
    """Con/sin www y otras terminaciones (.cl .com .co) del mismo nombre."""
    base = re.sub(r"^www\.", "", dominio)
    nombre, _, tld = base.partition(".")
    cand = [base, "www." + base]
    for t in ("com", "cl", "co"):
        if t != tld:
            cand += [f"{nombre}.{t}", f"www.{nombre}.{t}"]
    return cand


def consultar(dominio, desde, hasta, intentos=5):
    """Una captura por año con HTTP 200. Devuelve (lista, error). El ritmo y los bloqueos los maneja ritmo_archivo."""
    params = {
        "url": dominio, "output": "json", "from": str(desde), "to": str(hasta),
        "fl": "timestamp,original,statuscode", "filter": "statuscode:200",
        "collapse": "timestamp:4", "limit": "200",
    }
    try:
        datos = ritmo_archivo.obtener().consulta_cdx(params, intentos=intentos)
        return [{"timestamp": t, "original": o} for t, o, _ in datos[1:]], None
    except ritmo_archivo.ArchivoNoDisponible:
        raise
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"


def buscar_con_variantes(dominio, desde, hasta, con_variantes=True):
    """Devuelve (dominio_usado, snapshots, error). Prueba variantes solo si el original no tiene nada (y si se pidió)."""
    snaps, err = consultar(dominio, desde, hasta)
    if snaps:
        return dominio, snaps, None
    if err:
        return dominio, [], err  # falla de red: no es lo mismo que "sin capturas"
    if not con_variantes:
        return dominio, [], None
    for v in variantes(dominio)[1:]:
        snaps, err = consultar(v, desde, hasta)
        if snaps:
            return v, snaps, None
    return dominio, [], None


def verificar(desde, hasta, rehacer=False, con_variantes=True):
    filas = leer_dominios()
    previas = []
    if COBERTURA.exists() and not rehacer:
        with open(COBERTURA, newline="", encoding="utf-8") as fh:
            previas = list(csv.DictReader(fh))
        hechos = {r.get("dominio_original") or r["dominio"] for r in previas} | {r["dominio"] for r in previas}
        filas = [f for f in filas if f["dominio"] not in hechos]
        # Copia fechada antes de escribir: nada se pierde.
        hist = AQUI / "cobertura_historial"
        hist.mkdir(exist_ok=True)
        (hist / f"cobertura_{time.strftime('%Y%m%d_%H%M%S')}.csv").write_bytes(COBERTURA.read_bytes())
    out = []
    print(f"Revisando {len(filas)} dominios nuevos ({desde}-{hasta}); {len(previas)} ya estaban. No se descarga nada.\n")
    for i, f in enumerate(filas):
        escribir(f"Verificando cobertura {desde}-{hasta}", f["startup"], i, len(filas))
        usado, snaps, err = buscar_con_variantes(f["dominio"], desde, hasta, con_variantes)
        anios = sorted({s["timestamp"][:4] for s in snaps})
        if err:
            estado = f"ERROR de consulta ({err})"
        elif not anios:
            estado = "sin capturas (probadas variantes)" if con_variantes else "sin capturas (variantes sin probar)"
        else:
            estado = f"{len(anios)} años: {' '.join(anios)}"
        marca = f"  [variante: {usado}]" if usado != f["dominio"] and anios else ""
        print(f"  {f['startup']:<26} {f['dominio']:<26} {estado}{marca}")
        out.append({"startup": f["startup"], "dominio": usado, "n_anios": len(anios),
                    "anios": " ".join(anios),
                    "dominio_original": f["dominio"] if usado != f["dominio"] else "",
                    "error": err or ""})
        # Se guarda tras cada dominio para poder cortar y retomar sin perder lo hecho.
        _escribir_cobertura(previas + out)
    _escribir_cobertura(previas + out)
    con = sum(1 for r in out if r["n_anios"])
    escribir("Verificación terminada", f"{con} de {len(out)} nuevos con capturas", len(out), len(out),
             situacion="terminado")
    print(f"\n{con}/{len(out)} dominios nuevos con capturas. Detalle en {COBERTURA.name}")


def _escribir_cobertura(filas):
    with open(COBERTURA, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["startup", "dominio", "n_anios", "anios",
                                           "dominio_original", "error"])
        w.writeheader()
        w.writerows({c: f.get(c, "") for c in w.fieldnames} for f in filas)


DESCARTADAS = AQUI / "descartadas.csv"
CARPETA_DESCARTADAS = AQUI / "capturas_descartadas"


def es_negra(ruta):
    """True si la imagen es negro casi puro: el snapshot archivado está vacío."""
    im = Image.open(ruta).convert("L")
    im.thumbnail((200, 200))
    return ImageStat.Stat(im).mean[0] < 3


def cargar_descartadas():
    if not DESCARTADAS.exists():
        return set()
    with open(DESCARTADAS, newline="", encoding="utf-8") as fh:
        return {r["url_archivo"] for r in csv.DictReader(fh)}


def descartar(ruta, fila, motivo):
    """Mueve la captura a capturas_descartadas/ y lo registra; no se borra nada."""
    CARPETA_DESCARTADAS.mkdir(exist_ok=True)
    destino = CARPETA_DESCARTADAS / ruta.parent.name
    destino.mkdir(exist_ok=True)
    ruta.replace(destino / ruta.name)
    nuevo = not DESCARTADAS.exists()
    with open(DESCARTADAS, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["startup", "anio", "timestamp", "url_archivo", "motivo"])
        if nuevo:
            w.writeheader()
        w.writerow({"startup": fila["startup"], "anio": fila["anio"], "timestamp": fila["timestamp"],
                    "url_archivo": fila["url_archivo"], "motivo": motivo})


def cargar_indice():
    if not INDICE.exists():
        return {}
    with open(INDICE, newline="", encoding="utf-8") as fh:
        return {r["archivo"]: r for r in csv.DictReader(fh)}


def guardar_indice(filas):
    # Se escribe aparte y se reemplaza de una vez: quien lea indice.csv mientras se captura nunca ve un archivo a medias.
    tmp = INDICE.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_INDICE)
        w.writeheader()
        w.writerows(sorted(filas.values(), key=lambda r: (r["startup"], r["timestamp"])))
    tmp.replace(INDICE)


def repartir(snaps, n):
    """Elige n snapshots espaciados a lo largo del período (primero, último y los intermedios)."""
    if not n or len(snaps) <= n:
        return snaps
    if n == 1:
        return [snaps[0]]
    idx = sorted({round(i * (len(snaps) - 1) / (n - 1)) for i in range(n)})
    return [snaps[i] for i in idx]


ESPERA_MS = 45000  # tope de espera por página (antes 90000: casi siempre se agotaba sin alcanzar la red inactiva)
METODO = AQUI / "capturas_metodo.csv"


def ocultar_barra(pag):
    """Oculta la barra del archivo web. Si la página tiene scripts propios rotos, add_style_tag puede fallar:
    se prueba otra vía y, si tampoco anda, se sigue (la captura sirve igual; la barra queda visible)."""
    try:
        pag.add_style_tag(content=OCULTAR_BARRA)
        return True
    except Exception:
        try:
            pag.evaluate("css => { const s = document.createElement('style'); s.textContent = css; (document.head || document.documentElement).appendChild(s); }", OCULTAR_BARRA)
            return True
        except Exception:
            return False


FALLOS = AQUI / "capturas_fallos.csv"
MAX_FALLOS = 3   # una captura que falla tantas veces por motivos propios de la página se deja de insistir (se puede forzar)


# Motivos que vienen de la red del Mac y no de la página. Un corte de internet no dice nada sobre la pieza,
# así que estos fallos se siguen anotando en el CSV (queda el registro) pero no cuentan para MAX_FALLOS.
# Antes contaban: 1.498 de 1.860 fallos eran ERR_INTERNET_DISCONNECTED y dejaban piezas buenas fuera de la cola.
MOTIVOS_RED_LOCAL = ("ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_NETWORK_CHANGED", "ERR_ADDRESS_UNREACHABLE")


def es_fallo_de_red_local(motivo):
    """True si el motivo del fallo es un problema de la conexión del Mac y no de la página archivada."""
    t = str(motivo or "")
    return any(m in t for m in MOTIVOS_RED_LOCAL)


def cargar_fallos():
    """Fallos propios por url_archivo. Los cortes de la red local no se cuentan."""
    if not FALLOS.exists():
        return Counter()
    with open(FALLOS, newline="", encoding="utf-8") as fh:
        return Counter(r["url_archivo"] for r in csv.DictReader(fh)
                       if r.get("url_archivo") and not es_fallo_de_red_local(r.get("motivo")))


def anotar_fallo(url, ts, motivo):
    nuevo = not FALLOS.exists()
    with open(FALLOS, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["fecha", "url_archivo", "timestamp", "motivo"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), url, ts, str(motivo)[:200]])


NO_CAPTURABLES = AQUI / "capturas_no_capturables.csv"


def cargar_no_capturables():
    if not NO_CAPTURABLES.exists():
        return set()
    with open(NO_CAPTURABLES, newline="", encoding="utf-8") as fh:
        return {r["url_archivo"] for r in csv.DictReader(fh)}


def anotar_no_capturable(url, ts, motivo):
    """Snapshots que el archivo sirve como descarga y no como página: no se reintentan en cada lote."""
    nuevo = not NO_CAPTURABLES.exists()
    with open(NO_CAPTURABLES, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["url_archivo", "timestamp", "motivo"])
        w.writerow([url, ts, motivo])


def pagina_cargada(pag):
    """True si, pasado el tope, ya hay una página del archivo web en pantalla."""
    try:
        return (pag.url.startswith("https://web.archive.org/web/")
                and pag.evaluate("document.readyState") in ("interactive", "complete")
                and pag.evaluate("!!document.body && document.body.children.length > 0"))
    except Exception:
        return False


ANCHO_VENTANA = 1440
ALTOS_MAX_CSS = (40000, 16000, 8000)   # recortes de alto que se prueban si la página entera no se puede fotografiar


def sacar_captura(pag, destino):
    """Captura de página entera a doble resolución. Si el navegador no puede (por ejemplo, una página archivada sin estilos que
    se desborda 11.000 px a lo ancho), se recorta al ancho de la ventana y, si hace falta, al alto. Devuelve cómo se hizo ('' = normal)."""
    try:
        pag.screenshot(path=str(destino), full_page=True)
        return ""
    except Exception as e:  # noqa: BLE001
        if "Unable to capture screenshot" not in str(e):
            raise
    alto = int(pag.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"))
    ultimo = None
    for tope in ALTOS_MAX_CSS:
        h = max(1, min(alto, tope))
        try:
            pag.screenshot(path=str(destino), full_page=True, clip={"x": 0, "y": 0, "width": ANCHO_VENTANA, "height": h})
            return "recorte_ancho" if h == alto else f"recorte_ancho_alto_{h}"
        except Exception as e:  # noqa: BLE001
            if "Unable to capture screenshot" not in str(e):
                raise
            ultimo = e
    raise ultimo


PETICIONES = Path(__file__).resolve().parent / "capturas_peticiones.csv"


def anotar_metodo(url, ts, espera):
    """Anota cómo se esperó cada captura: 'networkidle' (como se pidió) o 'timeout_parcial'."""
    nuevo = not METODO.exists()
    with open(METODO, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["url_archivo", "timestamp", "espera", "tope_ms"])
        w.writerow([url, ts, espera, ESPERA_MS])


def capturar(desde, hasta, espera, muestra=0, solo_existentes=False, limite=0, reintentar_fallos=False):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    import json as _json

    # Listado de snapshots por dominio, en caché: las consultas al índice no se repiten en cada lote.
    cache_path = AQUI / "cdx_cache.json"
    cache = _json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    no_capturables = cargar_no_capturables()
    tope = False

    if not COBERTURA.exists():
        sys.exit("Corré primero: python capturar_corpus.py verificar")
    with open(COBERTURA, newline="", encoding="utf-8") as fh:
        cob = [r for r in csv.DictReader(fh) if int(r["n_anios"])]
    # Los dominios encontrados por variante (p. ej. .co en vez de .cl) no entran sin revisión.
    cob, omitidos = [r for r in cob if not r.get("dominio_original")], \
                    [r for r in cob if r.get("dominio_original")]
    # Solo dominios que, según cobertura.csv, tienen snapshots en el rango pedido: evita consultas al índice que se sabe que darían vacío.
    cob = [r for r in cob if any(desde <= int(a) <= hasta for a in r["anios"].split() if a.isdigit())]
    for r in omitidos:
        print(f"  - {r['startup']}: omitido, dominio por variante ({r['dominio']}) pendiente de revisión")
    gen = {f["startup"]: f.get("generacion", "") for f in leer_dominios()}
    indice = cargar_indice()
    descartadas = cargar_descartadas()
    if solo_existentes:
        # Completa solo startups que ya tienen piezas; no abre la captura a los demás dominios de cobertura.csv.
        con_piezas = {r["startup"] for r in indice.values()}
        cob = [r for r in cob if r["startup"] in con_piezas]
        print(f"  (solo startups con piezas: {len(cob)} dominios)")
    SALIDA.mkdir(exist_ok=True)
    nuevas = fallos = hechas = 0
    # Total estimado: años con captura según cobertura (o la muestra, si se pidió).
    def _anios_en_rango(r):
        return sum(1 for a in r["anios"].split() if a.isdigit() and desde <= int(a) <= hasta)
    total_gen = sum(min(_anios_en_rango(r), muestra) if muestra else _anios_en_rango(r) for r in cob)
    escribir("Capturando piezas del archivo web", hecho=0, total=total_gen)

    ritmo = ritmo_archivo.obtener(aviso=lambda t: escribir(
        "Capturando piezas del archivo web", t,
        situacion="pausado" if ("rechaz" in t or "sin responder" in t) else "en_curso"))
    fallos_previos = cargar_fallos()
    omitidas_por_fallos = 0
    cuenta = {"n": 0, "r429": 0}   # peticiones al archivo que dispara cada captura (la página trae sus imágenes, estilos y scripts)

    desglose = {}   # peticiones de la captura en curso según tipo de recurso y modificador de Wayback (im_, cs_, js_, id_, /_static/...)

    def al_pedir(req):
        if req.url.startswith("https://web.archive.org"):
            cuenta["n"] += 1
            m = re.match(r"https://web\.archive\.org/web/\d+([a-z]{2}_)?/", req.url)
            via = ("web/" + (m.group(1) or "pagina")) if m else ("_static" if "/_static/" in req.url else "otro")
            clave = f"{req.resource_type}:{via}"
            desglose[clave] = desglose.get(clave, 0) + 1

    def anotar_peticiones(startup, anio, ts, n, segundos):
        """Una fila por captura en capturas_peticiones.csv: de dónde salen las peticiones (medición, no cambia la captura)."""
        try:
            nuevo = not PETICIONES.exists()
            with open(PETICIONES, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if nuevo:
                    w.writerow(["fecha", "startup", "anio", "timestamp", "peticiones", "segundos", "desglose_tipo_via"])
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), startup, anio, ts, n, f"{segundos:.0f}",
                            _json.dumps(dict(sorted(desglose.items(), key=lambda x: -x[1])), ensure_ascii=False)])
        except OSError:
            pass

    def al_responder(resp):
        if resp.status == 429 and resp.url.startswith("https://web.archive.org"):
            cuenta["r429"] += 1

    with sync_playwright() as p:
        estado_nav = {"nav": None, "ctx": None, "pag": None}

        def abrir():
            for k in ("ctx", "nav"):
                try:
                    if estado_nav[k]:
                        estado_nav[k].close()
                except Exception:  # noqa: BLE001
                    pass
            estado_nav["nav"] = p.chromium.launch()
            estado_nav["ctx"] = estado_nav["nav"].new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            estado_nav["pag"] = estado_nav["ctx"].new_page()
            estado_nav["pag"].on("request", al_pedir)
            estado_nav["pag"].on("response", al_responder)

        abrir()
        try:
            for c in cob:
                clave = f"{c['dominio']}|{desde}|{hasta}"
                if clave in cache:
                    snaps, err = cache[clave], None
                else:
                    snaps, err = consultar(c["dominio"], desde, hasta)
                    if not err:
                        cache[clave] = snaps
                        cache_path.write_text(_json.dumps(cache), encoding="utf-8")
                if err:
                    print(f"  ! {c['startup']}: CDX falló ({err}); se reintenta en otra corrida")
                    continue
                carpeta = SALIDA / limpiar(c["startup"])
                carpeta.mkdir(exist_ok=True)
                total = len(snaps)
                snaps = repartir(snaps, muestra)
                print(f"  + {c['startup']}: {len(snaps)} de {total} snapshots")
                for s in snaps:
                    ts, anio = s["timestamp"], s["timestamp"][:4]
                    destino = carpeta / f"{anio}_{ts}.png"
                    rel = str(destino.relative_to(AQUI))
                    url = f"https://web.archive.org/web/{ts}/{s['original']}"
                    fila = {"startup": c["startup"], "generacion": gen.get(c["startup"], ""),
                            "anio": anio, "timestamp": ts, "url_archivo": url, "archivo": rel}
                    if url in descartadas or url in no_capturables:
                        hechas += 1   # ya resuelta antes: cuenta como avance en la barra de progreso
                        continue
                    if destino.exists():
                        if rel not in indice:
                            indice[rel] = fila
                            guardar_indice(indice)
                        hechas += 1
                        continue
                    if fallos_previos.get(url, 0) >= MAX_FALLOS and not reintentar_fallos:
                        omitidas_por_fallos += 1
                        hechas += 1
                        continue
                    escribir("Capturando piezas del archivo web", f"{c['startup']}, {anio}", hechas, total_gen)
                    bloqueos_aqui = reaperturas = 0
                    while True:
                        pag = estado_nav["pag"]
                        cuenta["n"] = cuenta["r429"] = 0
                        desglose.clear()
                        t0 = time.time()
                        try:
                            modo_espera = "networkidle"
                            try:
                                pag.goto(url, wait_until="networkidle", timeout=ESPERA_MS)
                            except PWTimeout:
                                # El archivo web carga los recursos despacio y la red casi nunca queda inactiva.
                                # Si la página ya está en pantalla se captura igual y queda anotado.
                                if not pagina_cargada(pag):
                                    raise
                                modo_espera = "timeout_parcial"
                            if cuenta["r429"]:
                                raise RuntimeError("HTTP 429 del archivo web durante la captura")
                            ocultar_barra(pag)
                            pag.wait_for_timeout(2500)
                            modo_captura = sacar_captura(pag, destino)
                            if modo_captura:
                                modo_espera = f"{modo_espera}+{modo_captura}"
                            if es_negra(destino):
                                descartar(destino, fila, "captura en negro: el snapshot archivado está vacío")
                                descartadas.add(url)
                                print(f"      {anio}  descartada (en negro)")
                            else:
                                indice[rel] = fila
                                guardar_indice(indice)
                                nuevas += 1
                                anotar_metodo(url, ts, modo_espera)
                                anotar_peticiones(fila.get("startup", ""), anio, ts, cuenta["n"], time.time() - t0)
                                print(f"      {anio}  ok" + ("" if modo_espera == "networkidle" else f" ({modo_espera})") + f" [{time.time() - t0:.0f} s, {cuenta['n']} peticiones]")
                            ritmo.exito()
                            ritmo.despues_de_captura(cuenta["n"], time.time() - t0)
                            break
                        except ritmo_archivo.ArchivoNoDisponible:
                            raise
                        except Exception as e:  # noqa: BLE001
                            destino.unlink(missing_ok=True)
                            msg = f"{type(e).__name__}: {str(e).splitlines()[0][:150] if str(e) else ''}"
                            if "Download is starting" in str(e):
                                anotar_no_capturable(url, ts, "el archivo web sirve este snapshot como descarga, no como página")
                                no_capturables.add(url)
                                fallos += 1
                                print(f"      {anio}  no capturable (descarga) {url}")
                                break
                            if "has been closed" in str(e) or type(e).__name__ == "TargetClosedError":
                                reaperturas += 1
                                if reaperturas > 4:
                                    raise RuntimeError("el navegador se cierra una y otra vez") from e
                                print(f"      {anio}  navegador cerrado; se abre uno nuevo y se reintenta")
                                abrir()
                                continue
                            if ritmo_archivo.es_bloqueo(msg) or cuenta["r429"]:
                                bloqueos_aqui += 1
                                print(f"      {anio}  el archivo rechazó la conexión ({msg}); se enfría y se reintenta")
                                ritmo.bloqueo(msg)
                                abrir()
                                if bloqueos_aqui <= 3:
                                    continue
                            fallos += 1
                            anotar_fallo(url, ts, msg)
                            print(f"      {anio}  FALLÓ [{time.time() - t0:.0f} s, {cuenta['n']} peticiones] {msg} {url}")
                            break
                    hechas += 1
                    if limite and nuevas >= limite:
                        tope = True
                        break
                if tope:
                    break
        finally:
            for k in ("ctx", "nav"):
                try:
                    if estado_nav[k]:
                        estado_nav[k].close()
                except Exception:  # noqa: BLE001
                    pass
    escribir("Captura terminada", f"{nuevas} piezas nuevas, {fallos} fallos", hechas, total_gen,
             situacion="terminado")
    print(f"\n{nuevas} piezas nuevas, {fallos} fallos. Índice: {INDICE.name} ({len(indice)} filas)")
    # Línea pensada para que un script de lotes la lea: dice si el lote se cortó por el límite (hay más) o si recorrió todo lo pendiente.
    print(f"ESTADO_LOTE: {'limite' if tope else 'completo'} nuevas={nuevas} fallos={fallos} omitidas_por_fallos={omitidas_por_fallos}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["verificar", "capturar"])
    ap.add_argument("--desde", type=int, default=2010)
    ap.add_argument("--hasta", type=int, default=2025)
    ap.add_argument("--espera", type=float, default=2.5, help="segundos entre capturas")
    ap.add_argument("--limite", type=int, default=0, help="detenerse tras N capturas nuevas (para lotes)")
    ap.add_argument("--solo-existentes", action="store_true",
                    help="capturar: solo startups que ya tienen piezas en indice.csv")
    ap.add_argument("--rehacer", action="store_true", help="verificar: volver a consultar todos los dominios")
    ap.add_argument("--sin-variantes", action="store_true", help="verificar: no probar variantes de dominio (con/sin www, .com, .cl, .co) cuando el original no tiene capturas")
    ap.add_argument("--reintentar-fallos", action="store_true", help="capturar: insistir con capturas que ya fallaron varias veces")
    ap.add_argument("--muestra", type=int, default=0,
                    help="capturar solo N años repartidos por startup (0 = todos)")
    a = ap.parse_args()
    try:
        if a.modo == "verificar":
            verificar(a.desde, a.hasta, a.rehacer, not a.sin_variantes)
        else:
            capturar(a.desde, a.hasta, a.espera, a.muestra, a.solo_existentes, a.limite, a.reintentar_fallos)
    except ritmo_archivo.ArchivoNoDisponible as e:
        print(f"\nESTADO_LOTE: sin_archivo {e}")
        escribir("Detenido: el archivo web no responde", str(e), situacion="error")
        sys.exit(3)
