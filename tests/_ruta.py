# -*- coding: utf-8 -*-
"""Pone la raíz del proyecto en sys.path para poder importar los módulos desde las pruebas."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for p in (str(RAIZ),):
    if p not in sys.path:
        sys.path.insert(0, p)
