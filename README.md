# Telvorn Automation — Pipeline de contenido para YouTube

Automatiza todo el proceso de subir un tema/LP menos la música en sí:
vídeo principal, Shorts, títulos, descripciones y hashtags.

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
   - Mac/Linux: `venv/bin/python subir_tema.py`
   - Windows: `.\venv\Scripts\python.exe subir_tema.py`
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

Condiciones de toda búsqueda:
- **Orientación según destino**: horizontal para el vídeo principal,
  vertical para los Shorts — se buscan por separado, cada uno con clips
  pensados para su formato en vez de recortar a lo bruto uno del otro.
- **Calidad mínima HD estricta**: un resultado sin ningún archivo de al
  menos 720p en su lado corto se descarta entero, no cae a una versión de
  menor calidad.
- **Emociones antes que objetos**: las búsquedas que genero priorizan
  escenas con una persona/situación que transmita un estado de ánimo
  concreto sobre objetos sueltos sin nadie que los habite.

Los Shorts ya admiten vídeo real como portada (antes solo imágenes fijas).
Si no tienes `PEXELS_API_KEY` o no se encuentra un clip vertical, el
asistente cae en generar una imagen con IA o en reutilizar la primera
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
- Terminal: `python programar_youtube.py` (o `venv/bin/python programar_youtube.py`).

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
python configurar_canal_youtube.py
```

### Lo que NO se puede automatizar por API (hazlo a mano en YouTube Studio)

- **Pantallas finales y tarjetas** dentro del vídeo (enlazar a otro vídeo/
  lista al final): Estudio → tu vídeo → Editor → Elementos → Pantalla
  final / Tarjetas.
- **Tráiler de canal** para quien no está suscrito: Estudio →
  Personalización → Diseño → "Vídeo destacado para visitantes que no
  están suscritos".
- **Comentario fijado** con enlaces en cada vídeo: entra al vídeo,
  publica el comentario, menú (⋮) → "Fijar".

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
