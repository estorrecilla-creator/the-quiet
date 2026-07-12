# Telvorn Automation — Pipeline de contenido para YouTube

Automatiza todo el proceso de subir un tema/LP menos la música en sí:
vídeo principal, Shorts, títulos, descripciones y hashtags.

## Modo súper simple (recomendado)

Una sola vez:
```bash
cd telvorn-automation
./setup.sh
```
Te instalará todo y creará `.env` — ábrelo y pon tu `ANTHROPIC_API_KEY`.

Cada vez que tengas un tema nuevo:
1. Copia el audio y la portada a `input/`.
2. Ejecuta:
   ```bash
   venv/bin/python subir_tema.py
   ```
3. Responde las preguntas (artista, título, género, contexto...) y espera.
4. Revisa el resultado en `output/`.

Eso es todo. El resto de este README explica el uso avanzado por línea de
comandos (`main.py` con flags), útil si quieres automatizar LPs completos o
integrarlo en otro script.

## Instalación manual (alternativa a ./setup.sh)

```bash
cd telvorn-automation
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

Todo queda como **borrador local**. Tú revisas y subes manualmente (o usas
`src/youtube_uploader.py` de forma independiente cuando quieras probar la
subida automática en modo privado).

## Siguiente fase: subida automática

Cuando queráis activar la subida directa a YouTube:
1. Sigue las instrucciones dentro de `src/youtube_uploader.py` (Google Cloud
   Console, credenciales OAuth).
2. Prueba primero con `privacy_status="private"`.
3. Cuando confíes en el pipeline, añade la llamada a `upload_video()` al
   final de `process_track()` en `main.py`.

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
