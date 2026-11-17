# Método de las medidas formales (`medidas.csv`)

Versión del método: **1**. Script: `medir_piezas.py`. Una fila por captura de `indice.csv`
(clave: `archivo`). Todas las medidas son mecánicas y reproducibles: mismo archivo de entrada,
mismo resultado. No hay juicio ni clasificación.

Cada fila lleva `startup`, `anio`, `timestamp`, `url_archivo` (URL completa del snapshot en el
archivo web) y `archivo` (ruta de la imagen), para volver siempre a la fuente.

## Origen de las imágenes

Capturas de pantalla de página completa hechas con Playwright + Chromium, viewport de 1440 × 900
píxeles CSS y `device_scale_factor = 2`, sobre `https://web.archive.org/web/<timestamp>/<url>` con la
barra del archivo web oculta. La imagen tiene el doble de píxeles que el tamaño CSS de la página.
Una captura depende de cómo el archivo web guardó la página: si el snapshot estaba vacío la imagen
es negra y se descarta (ver `descartadas.csv`).

## Medidas

| Columna | Qué es | Cómo se calcula |
|---|---|---|
| `ancho_px`, `alto_px` | Tamaño de la imagen en píxeles | Dimensiones del PNG. `alto_px` es el alto total de la página capturada (full page), con un mínimo de 1800 px: una página más corta que el viewport (900 px CSS) figura con 1800 px. |
| `ancho_css_px`, `alto_pagina_css_px` | Tamaño en píxeles CSS | `ancho_px / 2` y `alto_px / 2` (división entera). Supone `device_scale_factor = 2`, fijo en todas las capturas. |
| `color_1_hex` … `color_5_hex` | Cinco colores dominantes | Cada píxel se asigna a una de 4096 cubetas (4 bits por canal R, G, B; es decir, rangos de 16 niveles). Se ordenan las cubetas por cantidad de píxeles y se toman las 5 mayores. El color informado es el **promedio exacto de los píxeles de esa cubeta**, en hexadecimal. |
| `color_1_pct` … `color_5_pct` | Porcentaje de superficie | Píxeles de la cubeta sobre el total de píxeles de la imagen, en %, con dos decimales. |
| `n_colores_distintos` | Colores distintos | Cantidad de valores RGB exactos (24 bits) presentes en la imagen. No se agrupa ni se cuantiza. |
| `n_imagenes_html` | Imágenes embebidas | Cantidad de etiquetas `<img>` del HTML archivado crudo (`html_crudo/`). Incluye píxeles de seguimiento y logos pequeños. No cuenta imágenes de fondo CSS. |
| `n_formularios_html` | Formularios | Cantidad de etiquetas `<form>` del HTML archivado crudo. |
| `n_campos_formulario_html` | Campos de formulario | `<input>`, `<select>` y `<textarea>` dentro de un `<form>`, sin contar `hidden`, `submit`, `button`, `reset` ni `image`. |
| `caracteres_visibles` | Caracteres de texto visible | `n_caracteres_visibles` del JSON de `texto/` (Fase 1): texto del documento sin `script`, `style`, `noscript`, `template` ni `head`. |
| `prop_texto_vs_imagen` | Proporción de superficie de texto y de imagen | **No disponible** (ver abajo). |
| `version_metodo`, `fecha_medicion` | Versión del método y fecha | — |

## Límites que conviene citar

- **Paleta por cubetas:** dos tonos muy parecidos que caigan en la misma cubeta se suman, y dos
  tonos parecidos que caigan en cubetas vecinas se separan. Un degradado puede ocupar varias
  posiciones de la paleta. El método es fijo, por eso es comparable entre piezas, pero no
  equivale a la percepción humana del color.
- **Colores distintos:** las fotografías y los degradados elevan mucho la cifra; no mide
  "variedad de diseño", solo valores RGB exactos.
- **Texto vs. imagen:** requiere saber qué rectángulo ocupa cada elemento en la página
  renderizada. Una captura de pantalla sola no lo permite sin inferirlo, y las capturas se
  hicieron sin guardar la geometría del DOM. Por eso la columna dice `no disponible` y no hay
  estimación. Para obtenerla habría que volver a renderizar cada snapshot extrayendo los
  rectángulos de los elementos `<img>` y de los nodos de texto. Se puede agregar al script de
  captura para lo que se descargue de aquí en adelante.
- **HTML crudo:** el archivo web puede no haber guardado todos los recursos de la página. Un
  `<img>` presente en el HTML puede no haberse visto en la captura, y viceversa para imágenes
  de fondo.
- **Sesgos del archivo web:** conserva mejor los sitios con tráfico, pierde Flash y contenido
  cargado por JavaScript, y captura una sola versión de cada año (la primera con código 200).

## Reproducir

```bash
python medir_piezas.py     # agrega las piezas que faltan en medidas.csv
```

Dependencias: Python 3, `numpy`, `Pillow`, `beautifulsoup4` (versiones en `.venv`).
