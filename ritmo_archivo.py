# -*- coding: utf-8 -*-
"""
ritmo_archivo.py: control de ritmo y recuperación ante bloqueos para web.archive.org.

Por qué existe
  Una captura con navegador no es una petición: cada imagen, hoja de estilo y script de la página archivada
  es una petición a web.archive.org, así que una sola captura son decenas. El archivo no publica un límite,
  pero bloquea por IP cuando ve ráfagas: las conexiones empiezan a ser rechazadas (ConnectionRefused,
  ERR_EMPTY_RESPONSE) durante un rato. Reintentar enseguida lo empeora.

Qué hace
  - Reparte un presupuesto de peticiones por minuto (req_min) entre consultas CDX y capturas: tras cada captura
    espera lo que haga falta para que el promedio no pase el presupuesto.
  - Ante un bloqueo baja el presupuesto a la mitad, espera con enfriamiento creciente (con azar) y sondea con una
    consulta liviana hasta que el archivo vuelve a responder, antes de seguir.
  - Tras varios éxitos seguidos sube el presupuesto de a poco, hasta un techo. El valor aprendido queda en
    ritmo_estado.json y la próxima corrida parte de ahí.
  - Todo queda anotado en ritmo_eventos.csv para ver con datos qué ritmo aguanta el archivo.
"""

import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
ESTADO = AQUI / "ritmo_estado.json"
EVENTOS = AQUI / "ritmo_eventos.csv"
CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "Mozilla/5.0 (academic research; doctoral thesis)"}

REQ_MIN_INICIAL = 25      # presupuesto de partida, en peticiones por minuto (una captura son unas 100 a 130)
REQ_MIN_PISO = 3
REQ_MIN_TECHO = 90        # techo de prueba: 60 era el techo histórico. Si un bloqueo ocurre por encima de 60, el techo vuelve a 60 y queda guardado.
REQ_MIN_TECHO_SEGURO = 60
EXITOS_PARA_SUBIR = 8
EXITOS_PARA_SUBIR_LEJOS = 4   # mientras el presupuesto esté por debajo de la mitad del techo
CDX_INTERVALO_INICIAL = 3.0   # segundos entre consultas al índice (CDX); no depende del presupuesto de las capturas
CDX_INTERVALO_MAX = 30.0
CDX_EXITOS_PARA_ACELERAR = 40
SUBIDA = 1.15
SUBIDA_LEJOS = 1.4
ENFRIAMIENTO_INICIAL = 300    # segundos
ENFRIAMIENTO_MAX = 2700
PAUSA_MINIMA = 6              # segundos entre capturas, pase lo que pase
PAUSA_MAXIMA = 900            # una página con cientos de peticiones no frena más que esto
ESPERA_TOTAL_MAX = 6 * 3600   # si el archivo no vuelve en 6 horas, se corta la corrida con un aviso claro

MARCAS_BLOQUEO = ("ERR_CONNECTION_REFUSED", "ERR_EMPTY_RESPONSE", "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED",
                  "ERR_CONNECTION_TIMED_OUT", "ConnectionError", "Connection refused", "Connection reset",
                  "RemoteDisconnected", "Max retries exceeded", "Too Many Requests", " 429")


class ArchivoNoDisponible(RuntimeError):
    """El archivo no volvió a responder dentro del tiempo máximo de espera."""


def es_bloqueo(texto):
    t = str(texto)
    return any(m in t for m in MARCAS_BLOQUEO)


class Ritmo:
    def __init__(self, aviso=None):
        self.aviso = aviso or (lambda texto: None)   # función para mostrar en el estado en vivo qué se espera
        st = self._leer()
        self.req_min = float(st.get("req_min", REQ_MIN_INICIAL))
        self.techo = float(st.get("techo", REQ_MIN_TECHO))
        self.bloqueos = int(st.get("bloqueos", 0))
        self.cooldown = ENFRIAMIENTO_INICIAL
        self.exitos = 0
        self.cdx_intervalo = max(CDX_INTERVALO_INICIAL, float(st.get("cdx_intervalo", CDX_INTERVALO_INICIAL)))
        self.cdx_exitos = 0
        # Piso aprendido: el intervalo en que ya nos cortaron, con margen. Acelerar nunca baja de acá.
        self.cdx_piso = max(CDX_INTERVALO_INICIAL, float(st.get("cdx_piso", CDX_INTERVALO_INICIAL)))
        self._ultimo_cdx = 0.0
        self._ultima_baja = 0.0
        if not ESTADO.exists():
            self._guardar()

    # ---- persistencia y registro
    def _leer(self):
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar(self):
        tmp = ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"req_min": round(self.req_min, 2), "techo": self.techo, "cdx_intervalo": round(self.cdx_intervalo, 2), "cdx_piso": round(self.cdx_piso, 2), "bloqueos": self.bloqueos,
                                   "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(ESTADO)

    def registrar(self, evento, detalle=""):
        nuevo = not EVENTOS.exists()
        with open(EVENTOS, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if nuevo:
                w.writerow(["fecha", "evento", "req_min", "detalle"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), evento, round(self.req_min, 1), detalle])

    # ---- espera entre peticiones
    def esperar_cdx(self):
        """Las consultas al índice (CDX) tienen su propio ritmo: nunca más rápido que cada CDX_INTERVALO_INICIAL segundos."""
        falta = self._ultimo_cdx + self.cdx_intervalo - time.time()
        if falta > 0:
            time.sleep(falta)
        self._ultimo_cdx = time.time()

    def despues_de_captura(self, n_peticiones, segundos):
        """Espera lo que haga falta para que esta captura no pase el presupuesto por minuto."""
        necesario = (n_peticiones / self.req_min) * 60.0
        espera = min(PAUSA_MAXIMA, max(PAUSA_MINIMA, necesario - segundos))
        self.registrar("captura", f"{n_peticiones} peticiones en {segundos:.0f} s; espera {espera:.0f} s")
        fin = time.time() + espera
        while True:
            falta = fin - time.time()
            if falta <= 0:
                break
            self.aviso(f"pausa por el límite del archivo: faltan {falta:.0f} s")   # se renueva cada 30 s para que el estado no parezca congelado
            time.sleep(min(30, falta))

    # ---- éxitos y bloqueos
    def exito(self):
        self.exitos += 1
        # Lejos del techo (tras bloqueos seguidos el presupuesto llegó a 3 o 6 y la subida lenta tardó unas 13 horas en volver a 60) se sube
        # más rápido; cerca del techo se mantiene la subida cuidadosa. El techo no cambia: nunca pasa del que el archivo ya aguantó.
        lejos = self.req_min < self.techo / 2
        if self.exitos >= (EXITOS_PARA_SUBIR_LEJOS if lejos else EXITOS_PARA_SUBIR) and self.req_min < self.techo:
            self.req_min = min(self.techo, self.req_min * (SUBIDA_LEJOS if lejos else SUBIDA))
            self.exitos = 0
            self.cooldown = max(ENFRIAMIENTO_INICIAL, self.cooldown / 2)
            self.registrar("subida", "varios éxitos seguidos")
            self._guardar()

    def exito_cdx(self):
        """Una consulta al índice no mueve el presupuesto de las capturas: solo puede acelerar de a poco su propio intervalo."""
        self.cdx_exitos += 1
        if self.cdx_exitos >= CDX_EXITOS_PARA_ACELERAR and self.cdx_intervalo > self.cdx_piso:
            self.cdx_intervalo = max(self.cdx_piso, self.cdx_intervalo * 0.85)
            self.cdx_exitos = 0
            self.registrar("cdx_mas_rapido", f"intervalo {self.cdx_intervalo:.1f} s")
            self._guardar()

    def bloqueo(self, motivo, espera=None, via="captura"):
        """Registra el bloqueo, baja el ritmo de la vía que lo provocó y espera a que el archivo vuelva a responder.
        via='cdx': consultas al índice (se alarga su intervalo y se recuerda el piso). via='captura': páginas con navegador (baja el presupuesto
        de peticiones por minuto). Una vía no castiga a la otra: las capturas aguantaron horas a 25 a 38 peticiones por minuto mientras el índice
        se cortaba con unas 5 consultas por minuto."""
        self.exitos = 0
        self.cdx_exitos = 0
        self.bloqueos += 1
        if time.time() - self._ultima_baja > 600:   # un mismo episodio de bloqueo baja el ritmo una sola vez
            if via == "cdx":
                self.cdx_piso = min(CDX_INTERVALO_MAX, max(self.cdx_piso, self.cdx_intervalo * 1.5))
                self.cdx_intervalo = min(CDX_INTERVALO_MAX, max(self.cdx_intervalo * 2, self.cdx_piso))
            else:
                if self.req_min > REQ_MIN_TECHO_SEGURO and self.techo > REQ_MIN_TECHO_SEGURO:
                    self.techo = REQ_MIN_TECHO_SEGURO   # el archivo cortó por encima de 60: no se vuelve a probar
                    self.registrar("techo_a_60", f"bloqueo a {self.req_min:.0f} peticiones por minuto")
                self.req_min = max(REQ_MIN_PISO, self.req_min / 2)
            self._ultima_baja = time.time()
        pausa = espera if espera else self.cooldown * random.uniform(0.8, 1.2)
        self.registrar("bloqueo", f"{via}: {str(motivo)[:140]}; enfriamiento {pausa:.0f} s")
        self._guardar()
        self._esperar_archivo(pausa)
        self.cooldown = min(ENFRIAMIENTO_MAX, self.cooldown * 2)

    def _esperar_archivo(self, pausa):
        t0 = time.time()
        fin = t0 + pausa
        while time.time() < fin:
            self.aviso(f"el archivo rechazó conexiones; espera {max(0, fin - time.time()):.0f} s")
            time.sleep(min(30, max(1, fin - time.time())))
        intento = 0
        while True:
            try:
                # La sonda pregunta por una ruta distinta cada vez: una pregunta repetida podría contestarse desde la caché del archivo
                # y dar "ya volvió" mientras las consultas reales todavía se rechazan.
                r = requests.get(CDX, params={"url": f"example.com/sonda{random.randint(0, 10**9)}", "output": "json", "limit": "1"},
                                 headers=UA, timeout=30)
                if r.status_code == 200:
                    self.registrar("recuperado", f"tras {time.time() - t0:.0f} s")
                    return
                motivo = f"sonda HTTP {r.status_code}"
            except Exception as e:  # noqa: BLE001
                motivo = f"sonda {type(e).__name__}"
            if time.time() - t0 > ESPERA_TOTAL_MAX:
                self.registrar("rendido", f"sin respuesta tras {time.time() - t0:.0f} s")
                raise ArchivoNoDisponible(f"el archivo web no respondió en {ESPERA_TOTAL_MAX // 3600} horas")
            intento += 1
            extra = min(600, 60 * intento) * random.uniform(0.8, 1.2)
            self.aviso(f"el archivo sigue sin responder ({motivo}); reintento en {extra:.0f} s")
            time.sleep(extra)

    # ---- consulta CDX con el ritmo y los reintentos que corresponden
    def consulta_cdx(self, params, intentos=5, timeout=60):
        """Devuelve la respuesta JSON del CDX. Los bloqueos se enfrían y se reintentan; otros errores se reintentan poco."""
        ultimo = None
        for n in range(intentos):
            self.esperar_cdx()
            try:
                r = requests.get(CDX, params=params, headers=UA, timeout=timeout)
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After", "")
                    self.bloqueo("HTTP 429", espera=float(ra) if ra.isdigit() else None, via="cdx")
                    continue
                r.raise_for_status()
                datos = r.json()
                self.exito_cdx()
                return datos
            except ArchivoNoDisponible:
                raise
            except Exception as e:  # noqa: BLE001
                ultimo = f"{type(e).__name__}: {e}"
                if es_bloqueo(ultimo):
                    self.bloqueo(ultimo, via="cdx")
                else:
                    time.sleep(5 * (n + 1))
        raise RuntimeError(ultimo or "sin respuesta")


_RITMO = None


def obtener(aviso=None):
    """Una sola instancia por proceso."""
    global _RITMO
    if _RITMO is None:
        _RITMO = Ritmo(aviso)
    return _RITMO
