# startup-web-archive-pipeline

[![tests](https://github.com/agncris/startup-web-archive-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/agncris/startup-web-archive-pipeline/actions/workflows/tests.yml)

Python pipeline that rebuilds the historical web record of a list of startups from the Internet Archive's
Wayback Machine. It was developed for a doctoral research project on the Start-Up Chile program (2010-2025)
at the Doctorate in Design, Universidad de Palermo. Author: Cristian Aguilar.

The code is generic: it takes a list of startups with their domains and produces, per archived snapshot, a
screenshot, the raw HTML, extracted text, formal measurements, declared typography and lexical tables.

## Status

The pipeline has been run on the full Start-Up Chile cohort: 1,268 startups, 1,131 with archived snapshots,
and a universe of 7,337 startup-year pages (2010-2025), most of them already captured. Next step (Dec 2026 -
Feb 2027): detecting the third-party services embedded in each archived page (analytics, fonts, site builders,
CRM, chat, AI services) to measure platform dependence and lock-in over fifteen years, and comparing a
rule-based detector, an AI agent and a human reviewer on a hand-checked sample.

## What it does

1. Looks up which years each domain has an archived snapshot (CDX API, one HTTP 200 snapshot per year).
2. Captures a full-page screenshot of each snapshot with Playwright (Chromium, 1440 px wide, device scale 2,
   Wayback toolbar hidden, empty/black captures discarded).
3. Downloads the raw archived HTML (`id_` URLs, no Wayback rewriting) and extracts title, meta description,
   headings, buttons, action links, images and visible text into one JSON per snapshot.
4. Measures each capture: image size, five dominant colors, distinct colors, counts of images, forms and form
   fields, visible characters.
5. Reads the font families declared in the archived HTML and assigns them to broad typographic groups.
6. Builds frequency, series, shared-term and co-occurrence tables from the extracted text.
7. Produces contact sheets and per-year color palettes.

All steps are resumable and append-only; derived outputs keep their previous version in a `historial/` folder.
Requests to web.archive.org are rate-limited by `ritmo_archivo.py`, which backs off when the archive refuses
connections and remembers the pace that worked.

## Steps and scripts

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1. Coverage check | `capturar_corpus.py verificar` | `dominios.csv` | `cobertura.csv` |
| 1b. Retry failed lookups | `reverificar_errores.py` | `cobertura.csv` | `cobertura.csv` |
| 2. Screenshots | `capturar_corpus.py capturar` | `dominios.csv`, `cobertura.csv` | `capturas/`, `indice.csv` |
| 3. HTML and text | `extraer_texto.py` | `indice.csv` | `html_crudo/`, `texto/` |
| 4. Measurements | `medir_piezas.py` (`--completar` fills values that depend on HTML/text) | `indice.csv`, `capturas/` | `medidas.csv` |
| 5. Typography | `medir_tipografia.py` | `indice.csv`, `html_crudo/` | `tipografias.csv`, `reportes/` |
| 6. Lexical tables | `lexico.py` | `texto/` | `lexico/` |
| 7. Contact sheets, palettes | `hojas.py` | `indice.csv`, `medidas.csv` | `hojas/`, `paletas/` |

Support modules: `ritmo_archivo.py` (rate control), `versiones.py` (versioned writes), `estado.py` (optional
progress file). `run_pipeline.sh` runs the steps in order. The measurement method is documented in
`docs/medidas-metodo.md`.

### Input format

`dominios.csv` with columns `startup`, `dominio`, `generacion`, `notas`. Only `startup` and `dominio` are
required for the pipeline to work; rows without a domain are skipped. `sample/indice_muestra.csv` shows the
shape of `indice.csv` (the full index has the extra columns `generacion` and `archivo`, the path of each
screenshot).

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Run the whole sequence with `./run_pipeline.sh`, or each script on its own, for example
`.venv/bin/python capturar_corpus.py verificar --desde 2010 --hasta 2025`. Tests (no network needed):
`.venv/bin/python -m unittest discover -s tests`.

Data folders are created next to the scripts. Code comments and `docs/` are in Spanish.

## Scripts that need earlier output

Every script after step 1 depends on files produced by earlier steps and will not run on a clean checkout
without them: `capturar_corpus.py capturar` needs `cobertura.csv`; `extraer_texto.py`, `medir_piezas.py`,
`medir_tipografia.py` and `hojas.py` need `indice.csv` (and `capturas/` for the measurements and sheets);
`lexico.py` needs `texto/`. `sample/indice_muestra.csv` is only a sample of the index format and does not
include the screenshots, so it is not enough to run steps 4 and 7.

## Data policy

This repository contains code only. The archived pages are not redistributed: each page is referenced by its
Wayback Machine URL and 14-digit timestamp (for example
`https://web.archive.org/web/20180831120844/https://example.com/`). Screenshots, raw HTML, extracted text and
derived research tables are generated locally and excluded through `.gitignore`. Anyone can reproduce the
corpus by fetching the same URLs from the Internet Archive. Please respect the archive's terms of use and keep
the default request pace.

## Authorship

Built with Claude Code (Anthropic) as part of doctoral research. Author: Cristian Aguilar.

## License

MIT, see `LICENSE`.

## Citation

```
Aguilar, C. (2026). startup-web-archive-pipeline [Computer software]. [URL and DOI to be added].
```
