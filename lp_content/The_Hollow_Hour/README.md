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

Estrategia final (todo en viernes, mejor para listas editoriales):

1. **3 singles de avance** (fuera del orden narrativo, elegidos como
   "ganchos"): tema 10 (28 ago), tema 9 (4 sep), tema 2 (11 sep).
2. **Álbum completo el 18 de septiembre de 2026** — todos los temas
   quedan disponibles en streaming ese día. **Ese día no se sube ningún
   vídeo nuevo a YouTube**: se reserva para redirigir tráfico a
   Spotify/streaming (actualizar descripciones/comentario fijado de los
   singles ya publicados con el enlace al álbum completo — manual, ver
   sección de YouTube del README principal).
3. **Los 9 temas restantes**, en orden narrativo, 1 vídeo principal a la
   semana empezando el 25 de septiembre (la semana siguiente al álbum).
4. **Shorts**: para que salgan a ritmo de 2-3 por semana en vez de todos
   de golpe, al ejecutar `programar_youtube.py` para cada tema pon el
   intervalo entre publicaciones en 2-3 días (reparte el vídeo principal
   y sus 3 Shorts a lo largo de la semana).

DistroKid necesita ~30 días de antelación antes de cada fecha de
lanzamiento — no tiene API pública, así que hay que subirlo a mano en la
fecha límite (columna `distrokid_submit_by` del calendario).

**Aviso**: la primera fecha límite de DistroKid es el **29 de julio de
2026** — muy pronto, solo válido si el primer tema (el 10) ya está
masterizado y listo para entonces. Si no, avisa y recalculamos con una
fecha de inicio más realista.

Calendario completo en `calendario_lanzamiento.json`.
