#!/bin/bash
# run_pipeline.sh: runs the capture, extraction and measurement steps in order.
# Every step is resumable and only appends; derived outputs keep the previous version in historial/.
# Requires dominios.csv (columns: startup, dominio, generacion, notas) and a Python environment with
# requirements.txt installed. Set PY to use another interpreter, e.g. PY=python3 ./run_pipeline.sh
# Optional: DESDE and HASTA (years, default 2010 and 2025).
cd "$(dirname "$0")" || exit 1
PY="${PY:-.venv/bin/python}"
DESDE="${DESDE:-2010}"
HASTA="${HASTA:-2025}"
log() { echo "[$(date '+%F %T')] $*"; }
paso() {
  local nombre="$1"; shift
  log "START $nombre"
  "$@" || log "FAILED $nombre (code $?)"
  log "END $nombre"
}

paso "1. CDX coverage check"            $PY -u capturar_corpus.py verificar --desde "$DESDE" --hasta "$HASTA"
paso "2. Screenshot capture"            $PY -u capturar_corpus.py capturar --desde "$DESDE" --hasta "$HASTA"
paso "3. Raw HTML and text extraction"  $PY -u extraer_texto.py
paso "4. Formal measurements"           $PY -u medir_piezas.py
paso "4b. Complete measurements"        $PY -u medir_piezas.py --completar
paso "5. Declared typography"           $PY -u medir_tipografia.py
paso "6. Lexical tables"                $PY -u lexico.py
paso "7. Contact sheets and palettes"   $PY -u hojas.py
log "PIPELINE FINISHED"
