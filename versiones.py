# -*- coding: utf-8 -*-
"""
versiones.py — Nada se sobrescribe: antes de escribir una salida derivada que ya existe
(una tabla, una hoja de contacto), la versión anterior se mueve a <carpeta>/historial/
con la fecha en el nombre. Si el contenido nuevo es idéntico al existente no se hace nada.
"""

import hashlib
import shutil
import time
from pathlib import Path


def _hash(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def guardar_bytes(ruta, contenido):
    """Escribe `contenido` (bytes) en `ruta`. Devuelve True si hubo cambio."""
    ruta = Path(ruta)
    if ruta.exists():
        if hashlib.sha256(contenido).hexdigest() == _hash(ruta):
            return False
        hist = ruta.parent / "historial"
        hist.mkdir(exist_ok=True)
        shutil.move(str(ruta), hist / f"{ruta.stem}_{time.strftime('%Y%m%d_%H%M%S')}{ruta.suffix}")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return True


def guardar_texto(ruta, texto):
    return guardar_bytes(ruta, texto.encode("utf-8"))
