# -*- coding: utf-8 -*-
"""Pruebas del ritmo adaptativo. Sin red y sin tocar ritmo_estado.json ni ritmo_eventos.csv reales."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _ruta  # noqa: F401
import ritmo_archivo as ra


class PruebasRitmo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        for nombre, valor in (("ESTADO", d / "ritmo_estado.json"), ("EVENTOS", d / "ritmo_eventos.csv")):
            p = mock.patch.object(ra, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        # bloqueo() espera con _esperar_archivo, que duerme y consulta la red: se anula.
        p = mock.patch.object(ra.Ritmo, "_esperar_archivo", lambda self, pausa: None)
        p.start()
        self.addCleanup(p.stop)

    def ritmo(self, req_min, techo=ra.REQ_MIN_TECHO):
        ra.ESTADO.write_text(json.dumps({"req_min": req_min, "techo": techo}), encoding="utf-8")
        return ra.Ritmo()

    # ---- bloqueo
    def test_bloqueo_de_captura_baja_a_la_mitad(self):
        r = self.ritmo(40)
        r.bloqueo("ERR_CONNECTION_REFUSED", via="captura")
        self.assertEqual(r.req_min, 20)

    def test_bloqueo_nunca_baja_del_piso(self):
        r = self.ritmo(5)
        r.bloqueo("x", via="captura")
        self.assertEqual(r.req_min, ra.REQ_MIN_PISO)
        r._ultima_baja = 0   # simula que pasó el episodio anterior
        r.bloqueo("x", via="captura")
        self.assertEqual(r.req_min, ra.REQ_MIN_PISO)

    def test_bloqueo_por_encima_de_60_fija_el_techo_en_60(self):
        r = self.ritmo(80)
        r.bloqueo("x", via="captura")
        self.assertEqual(r.techo, ra.REQ_MIN_TECHO_SEGURO)
        self.assertEqual(r.req_min, 40)

    def test_un_episodio_baja_una_sola_vez(self):
        r = self.ritmo(40)
        r.bloqueo("x", via="captura")
        r.bloqueo("x", via="captura")
        self.assertEqual(r.req_min, 20)

    def test_bloqueo_del_cdx_no_toca_el_presupuesto_de_capturas(self):
        r = self.ritmo(40)
        r.bloqueo("HTTP 429", via="cdx")
        self.assertEqual(r.req_min, 40)

    # ---- subida
    def test_subida_lejos_del_techo_usa_subida_lejos(self):
        r = self.ritmo(10)   # menos de la mitad del techo (45)
        for _ in range(ra.EXITOS_PARA_SUBIR_LEJOS - 1):
            r.exito()
        self.assertEqual(r.req_min, 10)
        r.exito()
        self.assertAlmostEqual(r.req_min, 10 * ra.SUBIDA_LEJOS)

    def test_subida_cerca_del_techo_usa_subida(self):
        r = self.ritmo(60)
        for _ in range(ra.EXITOS_PARA_SUBIR - 1):
            r.exito()
        self.assertEqual(r.req_min, 60)
        r.exito()
        self.assertAlmostEqual(r.req_min, 60 * ra.SUBIDA)

    def test_nunca_pasa_del_techo(self):
        r = self.ritmo(85)
        for _ in range(ra.EXITOS_PARA_SUBIR):
            r.exito()
        self.assertEqual(r.req_min, ra.REQ_MIN_TECHO)
        for _ in range(ra.EXITOS_PARA_SUBIR * 3):
            r.exito()
        self.assertEqual(r.req_min, ra.REQ_MIN_TECHO)

    def test_subidas_repetidas_lejos_del_techo_terminan_en_el_techo(self):
        r = self.ritmo(ra.REQ_MIN_PISO, techo=60)
        for _ in range(500):
            r.exito()
        self.assertEqual(r.req_min, 60)

    def test_es_bloqueo(self):
        self.assertTrue(ra.es_bloqueo("net::ERR_CONNECTION_REFUSED at x"))
        self.assertFalse(ra.es_bloqueo("net::ERR_INTERNET_DISCONNECTED"))


if __name__ == "__main__":
    unittest.main()
