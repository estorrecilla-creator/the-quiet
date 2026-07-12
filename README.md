# Telvorn Automation — Pipeline de contenido para YouTube

Automatiza todo el proceso de subir un tema/LP menos la música en sí:
vídeo principal, Shorts, títulos, descripciones y hashtags.

## Instalación (una vez)

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

## Continuar el desarrollo con Claude Code

Este proyecto incluye `CLAUDE.md` con el contexto completo del estado actual
y las decisiones ya tomadas. Simplemente abre esta carpeta con Claude Code y
dile qué quieres añadir o cambiar — ya tiene todo el contexto que necesita.
