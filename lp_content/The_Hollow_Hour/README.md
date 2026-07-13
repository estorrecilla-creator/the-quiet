# THE HOLLOW HOUR — Contenido preparado para el pipeline

Artista: **It Was Time**
Género/estilo (usar el mismo para los 12 temas):
`Rock progresivo atmosférico, producción fría y distante, estética fotográfica analógica desaturada, nunca cálida ni pulida`

Cómo usar cada carpeta con `subir_tema.py`:
1. Copia tu audio del tema (una vez tengas el máster) a `input/`.
2. Cuando el asistente pregunte por la letra: si la carpeta del tema tiene `letra.txt`, dale esa ruta (sincroniza automático). Si no lo tiene (temas 1 y 11), el tema es instrumental — deja esa pregunta en blanco.
3. Cuando pregunte por artista/género/contexto: usa el artista y género de arriba, y pega el contenido de `contexto.txt` de la carpeta del tema como contexto — así las portadas generadas por IA mantienen la estética fría/analógica del álbum en vez de salir genéricas.
4. El resto del asistente (portadas, shorts, YouTube) funciona igual que siempre.

Orden de publicación sugerido: el de la tabla del dossier (1 a 12), es el orden narrativo del álbum.

## Decisiones cerradas (preguntas abiertas del dossier)

- **Fechas del proyecto**: enero–agosto 2026.
- **Idioma del canal de YouTube**: inglés.
- **Portada definitiva**: `assets/portada_final.jpg` — la imagen aportada por
  el usuario, con el nombre del álbum re-tipografiado en **Jura Medium**
  (antes tenía una tipografía distinta a la del nombre del grupo). Es la
  que se puede usar para el audio/DistroKid.
- **Miniaturas de YouTube por tema**: se generan a partir de
  `assets/portada_template.jpg` (la versión original, sin re-tipografiar)
  con `src/thumbnail_template.py`, que sustituye el texto del álbum por el
  título de cada tema — usa Jura Medium por defecto, coherente con la
  portada final.

## Calendario de lanzamiento

Estrategia: **singles escalonados**, un tema cada 14 días (quincenal),
siempre en viernes (mejor para listas editoriales). El contenido de
YouTube de cada tema no se publica hasta que ese tema ya esté disponible
en streaming (para no "filtrarlo" antes). DistroKid necesita ~30 días de
antelación antes de la fecha de lanzamiento — no tiene API pública, así
que hay que subirlo a mano en esa fecha límite.

Primer lanzamiento: **28 de agosto de 2026** (así que hay que subir el
primer tema a DistroKid antes del **29 de julio de 2026** — muy pronto,
solo si el primer tema ya está masterizado y listo para entonces; si no,
hay que mover esta fecha hacia adelante).

Calendario completo en `calendario_lanzamiento.json` (generado con
`calendario_lp.py`). Con 14 días de cadencia, el tema 12 se lanzaría a
finales de enero de 2027 — el tema 10 cae justo el 1 de enero (Año Nuevo),
puede convenir moverlo un par de días si se acerca esa fecha.
