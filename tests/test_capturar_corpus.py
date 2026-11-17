# -*- coding: utf-8 -*-
"""Pruebas del conteo de fallos de capturar_corpus. Sin red y con un CSV temporal."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _ruta  # noqa: F401

try:
    import capturar_corpus as cc
except Exception as e:  # noqa: BLE001
    cc = None
    ERROR_IMPORT = repr(e)


@unittest.skipIf(cc is None, "no se pudo importar capturar_corpus (dependencias)")
class PruebasFallos(unittest.TestCase):
    def escribir(self, filas):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        ruta = Path(d.name) / "capturas_fallos.csv"
        with open(ruta, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "url_archivo", "timestamp", "motivo"])
            for url, motivo in filas:
                w.writerow(["2026-11-17 10:00:00", url, "20200101000000", motivo])
        p = mock.patch.object(cc, "FALLOS", ruta)
        p.start()
        self.addCleanup(p.stop)
        return ruta

    def test_los_fallos_de_red_local_no_cuentan(self):
        self.escribir([("u1", "Error: net::ERR_INTERNET_DISCONNECTED at x"),
                       ("u1", "Error: net::ERR_NAME_NOT_RESOLVED"),
                       ("u1", "Error: net::ERR_NETWORK_CHANGED"),
                       ("u1", "Error: net::ERR_ADDRESS_UNREACHABLE"),
                       ("u2", "Error: Page.screenshot: Protocol error")])
        f = cc.cargar_fallos()
        self.assertEqual(f.get("u1", 0), 0)
        self.assertEqual(f["u2"], 1)

    def test_los_demas_fallos_si_cuentan(self):
        self.escribir([("u1", "TimeoutError: Page.goto: Timeout 60000ms exceeded")] * 3
                      + [("u1", "ERR_INTERNET_DISCONNECTED")] * 5)
        f = cc.cargar_fallos()
        self.assertEqual(f["u1"], 3)
        self.assertGreaterEqual(f["u1"], cc.MAX_FALLOS)

    def test_pieza_con_solo_cortes_de_red_no_queda_omitida(self):
        self.escribir([("u1", "ERR_INTERNET_DISCONNECTED")] * 10)
        self.assertLess(cc.cargar_fallos().get("u1", 0), cc.MAX_FALLOS)

    def test_sin_archivo_devuelve_vacio(self):
        with mock.patch.object(cc, "FALLOS", Path(tempfile.gettempdir()) / "no_existe_fallos_xyz.csv"):
            self.assertEqual(len(cc.cargar_fallos()), 0)

    def test_el_archivo_no_se_modifica(self):
        ruta = self.escribir([("u1", "ERR_INTERNET_DISCONNECTED"), ("u2", "otro")])
        antes = ruta.read_bytes()
        cc.cargar_fallos()
        self.assertEqual(ruta.read_bytes(), antes)

    def test_anotar_fallo_sigue_anotando_los_de_red(self):
        ruta = self.escribir([])
        cc.anotar_fallo("u1", "20200101000000", "net::ERR_INTERNET_DISCONNECTED")
        filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
        self.assertEqual(len(filas), 1)
        self.assertIn("ERR_INTERNET_DISCONNECTED", filas[0]["motivo"])


if __name__ == "__main__":
    unittest.main()
