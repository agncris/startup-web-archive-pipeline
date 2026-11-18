# -*- coding: utf-8 -*-
"""
estado.py — Escribe estado.js (progreso en vivo), que una página de seguimiento puede leer cada pocos segundos para mostrar
qué se está haciendo. Cada proceso aparece como una tarea (una línea) distinta.

Es un auxiliar opcional: lo importan los scripts de captura y medición para informar su avance.

Uso desde otros scripts:
    from estado import escribir
    escribir("Recolectando fichas", detalle="Sitio X, 2014", hecho=12, total=45)
    # la tarea se identifica por el nombre del script; se puede fijar con tarea="nombre"

Uso desde la terminal:
    python estado.py "Texto de la actividad" [--hecho 3 --total 10] [--tarea nombre] [--situacion terminado]
"""

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "estado.js"
CERRADURA = AQUI / ".estado.lock"


def _leer_tareas():
    if not SALIDA.exists():
        return {}
    for linea in SALIDA.read_text(encoding="utf-8").splitlines():
        if linea.startswith("window.TAREAS ="):
            try:
                return json.loads(linea.replace("window.TAREAS =", "").strip().rstrip(";"))
            except ValueError:
                return {}
    return {}


def escribir(actividad, detalle="", hecho=None, total=None, situacion="en_curso", tarea=None):
    """situacion: en_curso | pausado | terminado | error"""
    tarea = tarea or Path(sys.argv[0]).stem or "tarea"
    datos = {
        "tarea": tarea,
        "actividad": actividad,
        "detalle": detalle,
        "hecho": hecho,
        "total": total,
        "situacion": situacion,
        "actualizado": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(CERRADURA, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tareas = _leer_tareas()
        tareas[tarea] = datos
        contenido = ("window.ESTADO = " + json.dumps(datos, ensure_ascii=False) + ";\n"
                     "window.TAREAS = " + json.dumps(tareas, ensure_ascii=False) + ";\n")
        tmp = SALIDA.with_suffix(".js.tmp")
        tmp.write_text(contenido, encoding="utf-8")
        os.replace(tmp, SALIDA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("actividad")
    ap.add_argument("--detalle", default="")
    ap.add_argument("--hecho", type=int)
    ap.add_argument("--total", type=int)
    ap.add_argument("--tarea", default="manual")
    ap.add_argument("--situacion", default="en_curso",
                    choices=["en_curso", "pausado", "terminado", "error"])
    a = ap.parse_args()
    escribir(a.actividad, a.detalle, a.hecho, a.total, a.situacion, a.tarea)
    print(f"estado.js [{a.tarea}]: {a.actividad}")
