# -*- coding: utf-8 -*-
"""
reverificar_errores.py: vuelve a consultar al archivo web los dominios de cobertura.csv cuya consulta falló.

Solo toca las filas con `error`. Guarda una copia fechada en cobertura_historial/ y reescribe
cobertura.csv de forma atómica (archivo temporal y reemplazo), porque el lote de capturas puede
estar leyéndolo. Los snapshots nuevos que aparezcan entran solos al próximo lote.

Uso:
    .venv/bin/python reverificar_errores.py
"""

import csv
import os
import time
from pathlib import Path

import capturar_corpus as cc

AQUI = Path(__file__).resolve().parent
COBERTURA = AQUI / "cobertura.csv"
CAMPOS = ["startup", "dominio", "n_anios", "anios", "dominio_original", "error"]


def main():
    with open(COBERTURA, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    pendientes = [f for f in filas if f.get("error", "").strip()]
    print(f"{len(pendientes)} dominios con error de {len(filas)}")
    if not pendientes:
        return
    hist = AQUI / "cobertura_historial"
    hist.mkdir(exist_ok=True)
    (hist / f"cobertura_{time.strftime('%Y%m%d_%H%M%S')}.csv").write_bytes(COBERTURA.read_bytes())

    resueltos = 0
    for f in pendientes:
        original = f.get("dominio_original", "").strip() or f["dominio"]
        usado, snaps, err = cc.buscar_con_variantes(original, 2010, 2025)
        anios = sorted({s["timestamp"][:4] for s in snaps})
        if err:
            print(f"  sigue con error: {f['startup']} ({original}): {err[:80]}")
        else:
            resueltos += 1
            f["dominio"] = usado
            f["n_anios"] = str(len(anios))
            f["anios"] = " ".join(anios)
            f["dominio_original"] = original if usado != original and anios else ""
            f["error"] = ""
            print(f"  ok: {f['startup']} ({usado}): {len(anios)} años" + (f" {anios[0]}-{anios[-1]}" if anios else ""))
        time.sleep(2)

    tmp = COBERTURA.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows({c: f.get(c, "") for c in CAMPOS} for f in filas)
    os.replace(tmp, COBERTURA)
    print(f"{resueltos} resueltos, {len(pendientes) - resueltos} siguen con error.")


if __name__ == "__main__":
    main()
