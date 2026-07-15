# Telvorn Automation — Pipeline de contenido para YouTube

Automatiza todo el proceso de subir un tema/LP menos la música en sí:
vídeo principal, Shorts, títulos, descripciones y hashtags.

## Estructura de la carpeta

```
the-quiet/
├── tools/                    los asistentes que ejecutas tú (uno por tarea)
│   ├── subir_tema.py             un solo tema, paso a paso
│   ├── procesar_lp.py            el LP completo de una vez ("app" de escritorio)
│   ├── programar_youtube.py      calendarizar/subir un tema ya generado
│   ├── calendario_lp.py          calcular fechas de lanzamiento del LP
│   ├── configurar_canal_youtube.py   palabras clave/descripción del canal (1 vez)
│   ├── configurar_marca_agua.py      logo como watermark de YouTube (1 vez)
│   ├── continuar_subida_youtube.py   sigue subiendo un LP (sin preguntar nada,
│   │                              pensado para la Tarea Programada de Windows)
│   └── escalar_video.py          dar más nitidez a un clip suelto (opcional)
├── *.bat                     accesos directos de Windows a cada asistente de
│                              tools/ (estos SÍ se quedan en la raíz — son a
│                              los que apuntan tus iconos del escritorio)
├── main.py                   el motor: orquesta todo el pipeline
├── webapp.py + templates/    interfaz web opcional (Flask)
├── src/                      todos los módulos internos (audio, vídeo,
│                              YouTube, metadatos...) que usan main.py y tools/
├── assets/                   fuentes y recursos gráficos propios
├── lp_content/                contenido ya preparado de cada LP (letras,
│                              contexto, calendario...)
├── config/                    credenciales y memoria del asistente (nunca se
│                              sube a git)
├── MUSICA/                    <Grupo>/<LP>/ — audios+documento que tú pones,
│                              y AUDIO_FINAL/ VIDEOS/ SHORTS/ MINIATURAS/ que
│                              genera procesar_lp.py (tampoco se sube a git)
└── input/ output/ mastered/ normalized/ prepared/   carpetas de trabajo
                              (se crean solas, tampoco se suben a git)
```

Los `.bat` de la raíz no se han movido a propósito — son los que ya tienes
enlazados desde el escritorio, así que los accesos directos que ya creaste
siguen funcionando igual sin tener que rehacerlos.

## Modo súper simple (recomendado)

Necesitas [Python](https://python.org) instalado (marca "Add to PATH" durante
la instalación si estás en Windows) y **ffmpeg**:
- Mac: `brew install ffmpeg`
- Windows: `winget install ffmpeg` (o descarga desde ffmpeg.org y añádelo al PATH)
- Linux: `sudo apt install ffmpeg`

Una sola vez:

**Mac / Linux:**
```bash
cd the-quiet
./setup.sh
```

**Windows (PowerShell):**
```powershell
cd the-quiet
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Te instalará todo y creará `.env` — ábrelo con el Bloc de notas y pon tu
`ANTHROPIC_API_KEY`.

Cada vez que tengas un tema nuevo:
1. Copia el audio y la portada a `input/`.
2. Ejecuta:
   - Mac/Linux: `venv/bin/python tools/subir_tema.py`
   - Windows: `.\venv\Scripts\python.exe tools\subir_tema.py`
3. Responde las preguntas (artista, título, género, contexto...) y espera.
4. Revisa el resultado en `output/`.

### Acceso directo de escritorio (Windows, sin usar PowerShell)

Para no tener que abrir PowerShell cada vez:

1. En el Explorador de Windows, entra en la carpeta `the-quiet`.
2. Clic derecho sobre `subir_tema.bat` → **Enviar a** → **Escritorio (crear acceso directo)**.
3. A partir de ahora, doble clic en ese icono del escritorio abre una
   ventana y te va preguntando todo (audio, portada, título, contexto...)
   igual que si lo ejecutaras a mano, sin tener que escribir comandos.

Eso es todo. El resto de este README explica el uso avanzado por línea de
comandos (`main.py` con flags), útil si quieres automatizar LPs completos o
integrarlo en otro script.

## Instalación manual (alternativa a ./setup.sh)

```bash
cd the-quiet
python3 -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate
pip install -r requirements.txt
```

También necesitas **ffmpeg** instalado en el sistema:
- Mac: `brew install ffmpeg`
- Windows: descarga desde ffmpeg.org y añade al PATH
- Linux: `sudo apt install ffmpeg`

Copia `.env.example` a `.env` y pon tu API key de Anthropic:
```bash
cp .env.example .env
# edita .env y pon ANTHROPIC_API_KEY=sk-ant-...
```

`main.py` carga `.env` automáticamente (vía `python-dotenv`), así que no hace
falta exportar nada a mano.

## Uso — un solo tema

Pon el audio y la portada en `input/` (o donde prefieras) y ejecuta:

```bash
python main.py \
  --audio input/caminante.mp3 \
  --cover input/portada.jpg \
  --artist "Telvorn" \
  --title "Caminante" \
  --genre "doom-folk / post-rock / rock ibérico" \
  --context "Tema sobre la travesía de un caminante por un paisaje en ruinas" \
  --shorts 3
```

## Uso — LP completo

```bash
python main.py \
  --album-dir input/mi_lp/ \
  --cover input/portada.jpg \
  --artist "Iron Vigil" \
  --genre "early Black Sabbath, doom industrial" \
  --context "The Brimstone Testament — alegoría sobre el conflicto de Ormuz" \
  --shorts 2
```

Esto procesa todos los `.mp3`/`.wav` de la carpeta, uno por uno.

## Qué obtienes

Por cada tema, en `output/<nombre_del_tema>/`:
- `main_video.mp4` — vídeo horizontal para YouTube (portada + waveform)
- `main_video_metadata.json` — título, descripción, hashtags, tags SEO
- `short_1.mp4`, `short_2.mp4`, ... — Shorts verticales de los mejores momentos
- `short_N_metadata.json` — metadatos de cada Short

Todo queda como **borrador local**. Tú revisas y subes manualmente, o usas
`programar_youtube.py` para calendarizar y programar la subida automática
a YouTube (ver más abajo).

## Procesar un LP completo de una vez ("app" de escritorio)

`procesar_lp.py` automatiza el LP entero, tema a tema, sin tener que
arrastrar nada. Genera el vídeo principal + Shorts + metadatos + audio
final listo para DistroKid de todos los temas, con absolutamente todo lo
que tiene el pipeline (masterización, normalización de volumen, 15 clips
de vídeo libre de derechos por tema sin repetirse en todo el LP + 3 Shorts
por clip con su propio mejor momento de audio y de vídeo, letra karaoke,
marca de agua, acabado cinematográfico, miniatura por tema...). Al final,
si quieres, también encadena la programación/subida a YouTube de todo el
LP de golpe.

### Antes de arrancarlo

Dentro de `MUSICA/`, crea (si no existe ya) una carpeta con el nombre del
grupo, y dentro de esa una carpeta con el nombre del LP:

```
MUSICA/
  <Grupo>/
    <NombreDelLP>/
      <audios del LP>.zip  (o una carpeta con los audios dentro)
      <documento del LP>.txt   (concepto, letras y estilo por tema, en
                                 texto libre — no hace falta ninguna
                                 plantilla fija, Claude lo interpreta
                                 igual que lo haría una persona leyéndolo)
```

`MUSICA/` no se sube a git (son tus audios/vídeos, contenido tuyo, no
código) — créala tú la primera vez si no existe.

### Configurarlo como app de escritorio (Windows)

1. En el Explorador de Windows, entra en la carpeta `the-quiet`.
2. Clic derecho sobre `procesar_lp.bat` → **Enviar a** → **Escritorio
   (crear acceso directo)**.
3. A partir de ahora: doble clic en el icono del escritorio. Te pregunta
   el grupo y el LP (mostrándote los que ya existen en `MUSICA/`, para que
   no tengas que escribir el nombre exacto de memoria) y coge solo de ahí
   todo lo que necesita.

### Qué pregunta y qué no

Pregunta **una vez** al principio (artista/género, si quieres masterizar
contra una referencia, los logos de marca de agua, la plantilla de
miniatura, y los 4 primeros singles con sus fechas para calcular el
calendario de lanzamiento) y a partir de ahí no vuelve a interrumpir hasta
acabar todos los temas. Los audios se emparejan con los temas del
documento por orden/número (el primer audio con el tema nº1, etc.) — si el
número de audios y de temas no coincide, te avisa antes de continuar.

Por cada tema, en cuanto su audio está masterizado/normalizado, genera ya
su miniatura (la portada del LP con el nombre de ese tema, reutilizada
después para el vídeo principal y todos sus Shorts) y su audio final
(listo para subir a DistroKid) en `MUSICA/<Grupo>/<LP>/AUDIO_FINAL/`. Los
vídeos principales quedan en `VIDEOS/`, los Shorts en `SHORTS/` y las
miniaturas en `MINIATURAS/`, todo dentro de la carpeta del LP.

Si un tema falla a mitad (por ejemplo, no se encuentra portada para él),
no para todo el proceso: lo salta, sigue con el resto, y al final te
enseña un resumen de qué temas fallaron y por qué.

### El calendario de lanzamiento (singles + álbum completo)

Te pregunta cuáles son los 4 primeros lanzamientos (singles), en el orden
en que saldrán, la fecha del primero y la cadencia entre lanzamientos. Los
demás temas del LP se publican todos juntos, como álbum completo, después
del último single. Con eso calcula y guarda
`MUSICA/<Grupo>/<LP>/calendario_lanzamiento.json` — las fechas de
DistroKid son manuales (no hay API pública), así que esa parte la sigues
decidiendo/subiendo tú; el calendario solo te dice cuándo.

### La fase de YouTube (opcional, al final)

Si aceptas continuar, te pregunta un par de cosas más (idioma, lista de
reproducción, enlaces, hora del vídeo principal) y calcula el calendario
completo de publicación de todo el LP: los vídeos principales en sus
fechas de `calendario_lanzamiento.json`, y los Shorts a razón de 2 al día
(12:00 y 21:00, hora de España) — mientras se van publicando los temas,
uno del tema ya publicado y otro de avance del siguiente (antes de que
esté en streaming, a propósito: es la única excepción deliberada a "nunca
YouTube antes que streaming"); una vez publicados todos los temas, ambos
huecos tiran del resto de Shorts sin usar, sin repetir tema el mismo día,
hasta agotarlos (con 15 clips × 3 Shorts por tema, unos 9 meses de
publicaciones desde el primer single). Cada Short enlaza en su
descripción con el vídeo principal de su propio tema ("escucha el tema
completo") y cada vídeo principal con el siguiente tema del álbum
("sigue escuchando"), para mantener al oyente encadenado escuchando la
música en vez de saltar a otro canal. Como siempre, te enseña el
calendario completo **antes** de subir nada, y solo sube de verdad si lo
confirmas explícitamente — con su fecha de publicación ya fijada por
adelantado. La cuota gratuita de la API de YouTube solo da para subir
unos 5-6 vídeos al día (muy por debajo de los ~550 de un LP entero), así
que la subida en sí se reparte en varias tandas.

### Que el resto se suba solo, cada día (Tarea Programada de Windows)

En cuanto confirmas la subida, el programa te enseña un comando para
configurar (UNA sola vez) una Tarea Programada de Windows que se encarga
del resto — así no hace falta que relances nada a mano cada día:

1. Abre PowerShell y pega el comando que te enseñó `procesar_lp.py` (tiene
   esta forma, con la ruta de tu carpeta):
   ```powershell
   schtasks /create /tn "TelvornSubidaYouTube" /tr "C:\ruta\a\the-quiet\continuar_subida_youtube.bat" /sc daily /st 09:00
   ```
2. Listo. Todos los días a esa hora, Windows lanza solo
   `continuar_subida_youtube.py`, que sube el siguiente lote de vídeos de
   **todos** los LPs de `MUSICA/` que tengan una subida confirmada y
   pendiente (no hace falta repetir este paso por cada LP) y se para sola
   al llegar a la cuota diaria. No hace falta tener PowerShell, este
   programa ni ninguna ventana abiertos — ni tu usuario iniciado, si el
   PC está encendido.
3. El progreso queda registrado en `logs\subida_youtube.log`, por si
   quieres comprobar qué se subió cada día.
4. Truco: para que no se salte un día si el PC estaba apagado a esa hora,
   abre el Programador de tareas de Windows, busca "TelvornSubidaYouTube",
   entra en sus Propiedades → pestaña Configuración, y marca "Ejecutar la
   tarea tan pronto como sea posible después de una hora de inicio
   programada perdida".

## Preparación del audio (automática, dentro de `subir_tema.py`)

Antes de generar nada, `subir_tema.py` deja el audio en su mejor estado
posible, en una cadena de pasos (cada uno parte del resultado del
anterior):

1. **Masterización opcional** (`src/mastering.py`, con
   [Matchering](https://github.com/sergree/matchering) — gratis, local, de
   código abierto): te pregunta si quieres masterizar contra una canción
   de referencia con el sonido que buscas. Ajusta ecualización y volumen
   para parecerse a esa referencia, sin tocar el contenido de la canción
   (no corta ni reordena nada). Se guarda en `mastered/`.
2. **Recorte de silencio** al principio/final (`src/audio_hygiene.py`,
   siempre) — no toca el silencio de en medio, solo el tramo muerto antes
   de que arranque o después de que acabe la canción.
3. **Aviso de compatibilidad mono** (siempre, solo diagnóstico, no
   modifica nada): suma el audio a mono y avisa si pierde mucha energía
   (posible cancelación de fase por un estéreo muy ancho), algo que se
   nota en dispositivos que reproducen en mono.
4. **Reducción de ruido de fondo condicional** (siempre se comprueba,
   `src/audio_hygiene.py`) — solo se aplica una reducción muy conservadora
   (`afftdn`) si de verdad se detecta un suelo de ruido audible en los
   pasajes más flojos de la pista; si la mezcla ya está limpia (o no hay
   pasajes flojos con los que compararse), no se toca nada.
5. **Normalización de volumen y sample rate** (`src/loudness.py`, siempre)
   — lleva el volumen final a -14 LUFS (el estándar de YouTube/Spotify,
   con límite de pico real de -1 dBTP) y re-muestrea a 44.1kHz, para que
   ningún tema del canal suene más flojo/fuerte que otro ni se mezclen
   sample rates distintos entre masters de un mismo LP. Se guarda en
   `normalized/`.
6. **Limpieza de metadatos** (`src/metadata_cleaner.py`, siempre, el
   último paso): borra TODOS los metadatos que traiga el archivo —
   título, artista, comentarios, cualquier ID de generación o rastro de
   la herramienta usada para componerlo (Suno u otra) — y escribe en su
   lugar los correctos y limpios: título, artista, álbum, artista del
   álbum, número de pista/total (si vienes de `procesar_lp.py`, ej.
   "3/12"), número de disco (1/1 por defecto), género, año, compositor,
   letrista, productor, editorial, copyright y copyright fonográfico (℗).
   Un .wav guarda metadatos de dos formas distintas que ninguna
   herramienta lee todas (el chunk RIFF "LIST INFO" clásico, el que
   entienden el Explorador de Windows y la mayoría de comprobadores
   sencillos; y un chunk ID3v2 embebido, el que entienden ffprobe y
   muchos DAW/distribuidores, con más campos disponibles) — se escriben
   las dos, y ambas se borran primero por completo para no dejar pasar
   ningún rastro que ya trajera el archivo. Productor/editorial/copyright
   salen de `RELEASE_PUBLISHER` y `RELEASE_COPYRIGHT_HOLDER` en tu `.env`
   (si no los pones, se usa el nombre del artista). Este es el archivo
   final de verdad: el que se usa para generar los vídeos y el que puedes
   subir a DistroKid, sin ningún rastro de cómo se hizo.

   Los tres pasos anteriores (recorte de silencio, reducción de ruido y
   normalización) conservan el bit depth original del máster (24 bits si
   viene de Matchering) — sin fijarlo explícitamente, ffmpeg vuelca a 16
   bits por defecto en cada paso aunque la entrada sea de más calidad.

## Generar las portadas con IA (opcional)

Si no quieres crear las portadas a mano, `src/image_generator.py` las genera
directamente a partir de prompts de texto usando la API de imágenes de
OpenAI, y las descarga con el nombre correcto (`01.png`, `02.png`...) listas
para usar como `--cover input/mi_tema/` (varias portadas, una por movimiento
de cámara).

Configuración: añade `OPENAI_API_KEY=sk-...` a tu `.env` (crea una clave en
[platform.openai.com](https://platform.openai.com)). Uso de ejemplo:

```bash
python -m src.image_generator input/mi_tema "prompt de la primera portada" "prompt de la segunda"
```

## Vídeo libre de derechos en vez de imágenes con movimiento (opcional)

En vez de animar imágenes fijas con zoom/paneo, `src/stock_video.py` puede
buscar y descargar clips de vídeo de verdad (movimiento real, no simulado)
de bancos libres de uso comercial sin atribución — gratis, sin IA de pago.
`subir_tema.py` lo ofrece como opción al elegir la portada; si no encuentra
un clip que encaje para algún hueco, genera una imagen con IA en su lugar
(si tienes `OPENAI_API_KEY`), sin interrumpir el proceso.

Configuración: añade `PEXELS_API_KEY=...` a tu `.env` (clave gratuita,
aprobación instantánea, en [pexels.com/api](https://www.pexels.com/api/)).
Opcionalmente añade también `PIXABAY_API_KEY=...` (igual de gratuita, en
[pixabay.com/api/docs](https://pixabay.com/api/docs/)) y/o
`COVERR_API_KEY=...` (gratis, pero hay que pedirla por email a
team@coverr.co — [api.coverr.co/docs/start](https://api.coverr.co/docs/start/)):
se usan como fuentes de respaldo, probando primero Pexels, luego Pixabay,
luego Coverr, y quedándose con el primer clip válido — entre las tres hay
más posibilidades de encontrar uno que encaje para cada hueco. Basta con
tener una de las tres claves para activar la búsqueda de vídeo.

Todas las descargas se comprueban con `ffprobe` antes de aceptarlas (que
sea un vídeo de verdad, no un archivo cortado a mitad de descarga o un
HTML de error) — si sale corrupta, se descarta y se prueba con la
siguiente fuente en vez de arrastrar un archivo roto hasta el render
final.

Condiciones de toda búsqueda (se aplican igual en las tres fuentes):
- **Orientación según destino**: horizontal para el vídeo principal,
  vertical para los Shorts — se buscan por separado, cada uno con clips
  pensados para su formato en vez de recortar a lo bruto uno del otro.
- **Calidad mínima HD estricta**: un resultado sin ningún archivo de al
  menos 720p en su lado corto se descarta entero, no cae a una versión de
  menor calidad.
- **Emociones antes que objetos**: las búsquedas que genero priorizan
  escenas con una persona/situación que transmita un estado de ánimo
  concreto sobre objetos sueltos sin nadie que los habite.
- **Estética vintage 70-80 por defecto**: tanto las búsquedas de vídeo
  como los prompts de imagen con IA incluyen términos de look analógico
  (grano de película, colores desaturados/cálidos, textura de cine
  antiguo) salvo que el contexto del tema pida otra cosa.
- **Sin caras en primer plano ni mirando a cámara**: si una escena incluye
  una persona, tiene que estar de espaldas, de lejos o en silueta — nunca
  un rostro reconocible ni contacto visual con la cámara. Esto se aplica
  en dos capas: al generar las búsquedas (evitando términos como "face",
  "portrait" o "close-up") y como filtro de seguridad al elegir el
  resultado (se descarta cualquier vídeo cuya propia descripción —título
  en Pexels, tags en Pixabay— sugiera una cara en primer plano, aunque la
  búsqueda lo haya devuelto).

Los Shorts ya admiten vídeo real como portada (antes solo imágenes fijas).
Si no tienes ninguna de las dos claves o no se encuentra un clip vertical,
el asistente cae en generar una imagen con IA o en reutilizar la primera
imagen fija del vídeo principal, sin interrumpir el proceso.

### Vídeo principal: sin bucles visibles y color homogéneo

Para el vídeo principal (que puede durar varios minutos), un único clip
corto repitiéndose en bucle se nota mucho. El asistente sugiere
automáticamente cuántos clips buscar según la duración del tema (hasta 15),
para que cada uno cubra un tramo razonable sin loop evidente — puedes
subir ese número a mano si aun así se nota. También exige clips de al
menos 8s (en vez de 4s) para el vídeo principal.

Como los clips vienen de fuentes distintas, cada uno trae su propia
exposición/color. `src/color_match.py` analiza el brillo medio de todos
los clips descargados y corrige cada uno hacia un punto medio común
(`eq=brightness` + saturación fija), para que el salto de un clip a otro
se note menos — además de las transiciones (fundidos, barridos...) que ya
había entre cada dos.

Entre dos **clips de vídeo real** (no imágenes), la transición nunca es
un fundido cruzado ni un barrido — esos componen los dos vídeos en
pantalla a la vez durante el solape (dos movimientos independientes
superpuestos, que se ve confuso). Ahí se usa siempre un fundido a negro
(`fadeblack`): cada clip se apaga/enciende contra negro por separado, sin
mezclar directamente el contenido de los dos. Entre imagen-imagen o
imagen-vídeo sí se siguen usando las transiciones variadas de siempre.

Los cortes entre clips, además, caen en un cambio real de la música en
vez de a mitad de una nota: `src/cover_sequence.py` detecta los
ataques/onsets de la pista (con `librosa`, ya lo usamos para los Shorts) y
"engancha" cada corte al más cercano dentro de una ventana de unos
segundos alrededor del reparto uniforme — si no hay ningún ataque cerca
de un punto, se queda con el reparto uniforme para ese corte, sin errores.

### Acabado cinematográfico discreto

Tanto el vídeo principal como los Shorts llevan, siempre, una viñeta
suave + grano fino + un ligero toque de color entre sombras y luces
(`src/cinematic_grade.py`, todo con filtros nativos de ffmpeg) sobre la
capa de fondo — antes de superponer la forma de onda, la letra o la marca
de agua, para no ensuciar la legibilidad del texto ni oscurecer sus
esquinas con la viñeta.

### Letra en karaoke, palabra a palabra

La letra sincronizada (`src/lyrics.py`) ya no se muestra línea a línea de
golpe: cada palabra se resalta (blanco → lavanda, el mismo color de acento
que la barra de forma de onda) según le toca cantarse. No tenemos el
tiempo exacto de cada palabra suelta (solo el de la línea completa vía
reconocimiento de voz), así que se reparte proporcionalmente a la
longitud de cada palabra — no es perfecto al 100%, pero se nota mucho más
vivo que la línea entera estática.

## Programar la publicación en YouTube

Una vez tienes el vídeo principal y los Shorts de un tema en `output/`, hay
un asistente aparte para calendarizar y subir todo a YouTube ya programado
(se publica solo, en la fecha y hora que elijas, sin tener que volver a
tocar nada ese día).

Configuración previa (una sola vez):
1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com).
2. Activa "YouTube Data API v3".
3. Crea credenciales OAuth 2.0 (tipo "Desktop app") y descarga el
   `client_secret.json` → guárdalo en `config/client_secret.json` (esa
   carpeta está en `.gitignore`, nunca se sube).
4. La primera vez que subas algo se abrirá el navegador para autorizar la
   cuenta del canal; después queda guardado en `config/token.json`.

Uso:
- Windows: doble clic en `programar_youtube.bat` (o crea un acceso directo
  igual que con `subir_tema.bat`).
- Terminal: `python tools/programar_youtube.py` (o `venv/bin/python tools/programar_youtube.py`).

Te pedirá la carpeta de salida del tema (ej. `output/Mi_Tema`), la fecha y
hora del primer envío (hora de España) y cada cuántos días quieres publicar
el siguiente (vídeo principal primero, luego los Shorts). Te enseña el
calendario propuesto y lo guarda en `calendario.json` dentro de esa carpeta
**antes** de subir nada — puedes revisarlo o editarlo a mano. Solo sube y
programa de verdad si confirmas explícitamente.

**Nota si ya lo tenías configurado de antes**: el permiso pedido a Google
se ha ampliado (de "solo subir vídeos" a "gestión completa del canal", para
poder crear listas de reproducción). Borra `config/token.json` para que la
próxima subida te pida autorizar de nuevo con el permiso ampliado.

### Miniaturas por tema, con contraste automático

Si le das una plantilla (la portada del LP con el logo/nombre de grupo/
álbum ya diseñada), `src/thumbnail_template.py` genera una miniatura por
tema sustituyendo el nombre del álbum por el título del tema, sin tocar
el resto del diseño. El color del texto se elige automáticamente según el
brillo real del fondo de la plantilla (gris claro sobre fondos oscuros,
gris oscuro sobre fondos claros) — así funciona igual de bien con
cualquier portada futura, no solo con fondo negro como "The Hollow Hour".
Si no das plantilla, se usa un fotograma del propio vídeo como miniatura.

### Listas de reproducción y enlaces en la descripción

Al confirmar la subida, también te pregunta:
- **Nombre de una lista de reproducción** (ej. el nombre del LP): si la
  das, crea la lista (o reutiliza la que ya exista con ese nombre — no
  duplica) y añade ahí el vídeo principal, en la posición correcta si el
  título del tema empieza por un número (ej. "10 Static Between Hands
  (Reprise)" → posición 10). El enlace a esa lista se añade automáticamente
  a la descripción de todos los vídeos y Shorts de ese tema.
- **Enlaces extra** (redes, web...): lo que pegues se añade tal cual al
  final de la descripción de todos los vídeos/Shorts de esa tanda.

### Ajustar el canal (palabras clave, "Acerca de")

`configurar_canal_youtube.py` — asistente aparte para las palabras clave y
la descripción del canal (ayuda a que YouTube lo recomiende al nicho
correcto). Se ejecuta una vez, o cuando quieras cambiarlas:
```bash
python tools/configurar_canal_youtube.py
```

### Marca de agua: nombre del grupo/tema y logo, discretos

Dos piezas complementarias, pensadas para no chocar nunca con la letra
sincronizada ni la barra de forma de onda (que ocupan la franja inferior,
casi a todo lo ancho):

- **Vídeo principal**: el nombre del tema se queda quemado, pequeño y
  semitransparente, en la esquina **superior izquierda** (automático, sin
  preguntar nada — `subir_tema.py` ya le pasa el título). El logo del
  grupo NO se quema aquí: se configura **una sola vez** como watermark
  nativo de YouTube (`configurar_marca_agua.py`), que a partir de ahí lo
  superpone solo en todos tus vídeos largos, sin tocar nada más. YouTube
  coloca ese watermark en la esquina **superior derecha** — por eso el
  nombre del tema va a la izquierda, para que nunca se pisen:
  ```bash
  python tools/configurar_marca_agua.py
  ```
  Usa un PNG con fondo transparente (el logo "sin fondo" que comentábamos).
- **Shorts**: como YouTube no aplica su watermark de canal a los Shorts,
  ahí sí se queman los dos juntos (logo + nombre del tema), también en la
  esquina superior izquierda. Al no llevar fondo, el logo necesita
  contraste con lo que tenga detrás en cada Short — por eso `subir_tema.py`
  te pide **dos variantes**, una clara y otra oscura (basta con una si no
  tienes las dos). Antes de generar cada Short, `src/watermark.py` mide el
  brillo medio de la esquina superior izquierda del propio vídeo/imagen de
  portada de ese Short (muestreando varios fotogramas si es un clip) y
  elige la variante clara sobre fondos oscuros o la oscura sobre fondos
  claros — automático, sin tener que mirarlo tema a tema. Las rutas se
  recuerdan entre ejecuciones (`config/asistente_memoria.json`); si no das
  ningún logo, el Short lleva solo el nombre del tema.

### Lo que NO se puede automatizar por API (hazlo a mano en YouTube Studio)

- **Pantallas finales y tarjetas** dentro del vídeo (enlazar a otro vídeo/
  lista al final): Estudio → tu vídeo → Editor → Elementos → Pantalla
  final / Tarjetas.
- **Tráiler de canal** para quien no está suscrito: Estudio →
  Personalización → Diseño → "Vídeo destacado para visitantes que no
  están suscritos".
- **Comentario fijado** con enlaces en cada vídeo: entra al vídeo,
  publica el comentario, menú (⋮) → "Fijar".

## Dar más nitidez a un clip suelto (opcional, necesita GPU)

Si algún clip de stock llega justo de calidad (justo en el mínimo HD),
`escalar_video.py` puede escalarlo x2 o x4 con IA (Real-ESRGAN, a través
de [Video2X](https://docs.video2x.org/installing/index.html) — gratis, de
código abierto). No forma parte del pipeline automático: es una
herramienta aparte para usar clip a clip cuando tú decidas que uno lo
necesita, no todos los sacados de Pexels/Pixabay/Coverr valen la pena
escalar.

Necesita tener Video2X instalado por separado (el instalador de Windows
lo añade al PATH) y una GPU con soporte Vulkan medianamente decente — sin
ella el proceso es demasiado lento para ser práctico. Si no lo tienes, no
pasa nada: el resto del pipeline funciona exactamente igual sin este paso.

```bash
python tools/escalar_video.py
```

## Publicar en Facebook e Instagram

`src/meta_uploader.py` ya está listo para publicar en una Página de
Facebook y en la cuenta de Instagram (Business/Creator) vinculada a ella.
No hace falta el ordenador para leer esto, pero sí para configurarlo:

1. Crea una app en [developers.facebook.com](https://developers.facebook.com).
2. Pide la revisión de los permisos `pages_show_list`,
   `pages_read_engagement`, `pages_manage_posts` e
   `instagram_content_publish`. **Esto puede tardar días** — conviene
   pedirlo cuanto antes, aunque tardemos en usarlo.
3. Vincula tu cuenta de Instagram (Business/Creator) a tu Página de
   Facebook, desde la configuración de la Página.
4. Genera un token de acceso de Página de larga duración (Graph API
   Explorer → intercambio de token) y añade a tu `.env`:
   `PAGE_ID`, `PAGE_ACCESS_TOKEN`, `IG_USER_ID`.

Diferencias importantes frente a YouTube:
- **Facebook sí soporta programar la publicación** (se sube ya, y Meta lo
  publica solo en la fecha que le digas), igual que YouTube.
- **Instagram no tiene programación nativa por API**: hay que llamar a la
  función de publicar justo en el momento exacto en que quieres que salga.
  Para eso hace falta algo que "despierte" en esa fecha (por ejemplo, el
  Programador de tareas de Windows) y dispare la publicación entonces.
- **Instagram no acepta un archivo local**: necesita una URL pública desde
  la que descargar el vídeo, así que hay que alojarlo en algún sitio
  (aunque sea temporalmente) antes de publicar. Es el paso que más se
  puede complicar — lo resolvemos cuando lleguemos a esta parte.

Uso de ejemplo (una vez configurado):
```bash
python -m src.meta_uploader facebook input/mi_video.mp4 "descripción del vídeo"
python -m src.meta_uploader instagram https://tu-hosting.com/video.mp4 "caption del reel"
```

## Web app / uso desde el móvil (iPhone incluido)

Hay una interfaz web (`webapp.py`) para generar contenido desde el navegador
(Safari en iPhone funciona bien) sin usar la terminal: subes audio + portada,
rellenas artista/título/género/contexto, y descargas los vídeos y metadatos
cuando terminan.

**Importante:** esto es software local que corre `ffmpeg`, no puede vivir
"en tu iPhone" como una app nativa. Lo que sí puedes hacer es desplegarlo en
un servidor (gratis o muy barato) y entrar a él desde el navegador del móvil.

### Probarlo en tu ordenador primero

```bash
./setup.sh                       # si no lo has hecho ya
venv/bin/pip install -r requirements-web.txt
export APP_PASSWORD=algo-secreto  # protege el acceso, si no nadie más podría usar tu API key
venv/bin/python webapp.py
```
Abre `http://localhost:5000` en el navegador.

### Desplegarlo para usarlo desde el iPhone (Render.com)

1. Ve a [render.com](https://render.com) y crea una cuenta (gratis).
2. "New" → "Web Service" → conecta tu cuenta de GitHub → elige el repo
   `the-quiet`. Render detecta el `render.yaml` y el `Dockerfile` solo.
3. Cuando te pida las variables de entorno, añade:
   - `ANTHROPIC_API_KEY` = tu clave de Anthropic
   - `APP_PASSWORD` = una contraseña que te inventes (para que no sea público)
4. Despliega. Te da una URL tipo `https://telvorn-automation.onrender.com`.
5. En el iPhone, abre esa URL en Safari → botón compartir → **"Añadir a
   pantalla de inicio"**. Te queda como un icono más, se abre a pantalla
   completa.

Notas:
- El plan gratuito de Render "duerme" el servicio si no lo usas — la primera
  carga tras un tiempo sin actividad puede tardar ~30s en arrancar.
- Generar un vídeo real (audio de varios minutos + varios Shorts) puede
  tardar unos minutos; la página de estado se actualiza sola cada 5s.
- Los archivos generados no son permanentes en el plan gratuito (el disco es
  efímero): descárgalos en cuanto estén listos, no los dejes ahí.
- Para que la sesión de login no se cierre en cada redeploy, fija también
  `FLASK_SECRET_KEY` a un valor tuyo (si no, Render genera uno al desplegar,
  lo cual también vale).

## Continuar el desarrollo con Claude Code

Este proyecto incluye `CLAUDE.md` con el contexto completo del estado actual
y las decisiones ya tomadas. Simplemente abre esta carpeta con Claude Code y
dile qué quieres añadir o cambiar — ya tiene todo el contexto que necesita.
