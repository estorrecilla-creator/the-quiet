# Contexto del proyecto — Automatización de contenido musical

## Qué es esto
Pipeline que automatiza TODO el proceso de publicación de una canción/LP en
YouTube, excepto la composición/producción musical (eso lo hace Salva).

Input: audio (mp3/wav) + portada (jpg/png)
Output: vídeo largo para YouTube + N Shorts + títulos/descripciones/hashtags,
todo en carpetas listas para revisión manual antes de subir.

## Estado actual (pipeline verificado end-to-end con audio sintético, wav y mp3)
- `src/audio_analysis.py` — detecta mejores momentos (energía + onsets). FUNCIONA.
- `src/video_generator.py` — vídeo horizontal con waveform sobre portada. FUNCIONA.
- `src/shorts_generator.py` — shorts verticales 1080x1920 recortados de los
  mejores momentos, con fade in/out. FUNCIONA.
- `src/metadata_generator.py` — título/descripción/hashtags vía API de Claude
  (modelo `claude-sonnet-5`). Requiere ANTHROPIC_API_KEY. Se corrigió un bug:
  usaba un model id inválido (`claude-sonnet-4-6`) que habría fallado incluso
  con API key correcta. Lógica de parseo del JSON verificada con mock; falta
  confirmación en vivo con una ANTHROPIC_API_KEY real (no disponible en el
  entorno de desarrollo/sandbox).
- `src/youtube_uploader.py` — sube en modo PRIVADO vía OAuth. NO PROBADO
  (necesita client_secret.json de Google Cloud Console, no se puede generar
  automáticamente). Salva decidió: de momento NO integrar en el pipeline
  automático, dejar como módulo aparte hasta que se confirme el flujo.
- `main.py` — orquestador CLI que encadena todo. Carga `.env` automáticamente
  (`python-dotenv`) y falla con un mensaje claro si falta ANTHROPIC_API_KEY,
  en vez de dejar pasar un traceback críptico.
- `subir_tema.py` — asistente interactivo por terminal (pregunta ruta de
  audio/portada, artista, título, género, contexto, nº de shorts) que llama
  a `process_track()` de `main.py`. Pensado para que Salva no tenga que
  recordar flags de CLI.
- `setup.sh` — instalación de un solo comando (venv + deps + crea `.env`).
- `webapp.py` + `templates/` — interfaz web (Flask) para generar contenido
  desde el navegador (incluido Safari en iPhone) sin terminal: formulario de
  subida (audio + portada + campos), job en background con hilo, página de
  estado con auto-refresh, descarga de resultados. Protegida por contraseña
  opcional (`APP_PASSWORD`) vía sesión. Probada end-to-end con el test client
  de Flask (login, subida, polling de estado, descarga) usando metadatos
  simulados. `Dockerfile` + `render.yaml` listos para desplegar en Render.com
  (`requirements-web.txt` añade flask/gunicorn sobre `requirements.txt`).

El pipeline se probó de punta a punta (`process_track` con audio real .wav/.mp3
sintético + portada) generando vídeo principal, N shorts y JSONs de metadatos
sin errores, tanto por CLI (`main.py`/`subir_tema.py`) como vía la webapp.
Para uso real solo falta: (1) que el usuario ponga su ANTHROPIC_API_KEY real
en `.env` (CLI) o como variable de entorno del servicio desplegado (web), y
(2) copiar sus temas + portada a `input/` o subirlos por el formulario web.

## Decisiones de diseño ya tomadas (no las cambies sin confirmar con Salva)
- Estilo de vídeo principal: waveform/visualizador sobre portada (no lyric
  video, no vídeo estático simple). Elegido por ser automatizable sin
  depender de letras sincronizadas.
- Modo de publicación: BORRADOR. El pipeline genera los archivos, Salva los
  revisa y sube manualmente (o los publica como privado). NO hay subida
  automática pública todavía — se activará en una fase posterior.
- Selección de mejores momentos: combina energía RMS + fuerza de onset al
  inicio del clip (para no cortar a media frase musical), con non-max
  suppression para que los momentos no queden pegados unos a otros.

## Próximos pasos pendientes (backlog)
1. Confirmar `metadata_generator.py` con una ANTHROPIC_API_KEY real (lógica
   ya verificada con mock, solo falta la llamada real de Salva en su máquina).
2. Añadir plantilla de estilo visual de marca (tipografía/logo del grupo
   superpuesto en los vídeos — actualmente es solo portada + waveform).
3. Soporte para letras sincronizadas (si el grupo decide hacer lyric videos
   para algunos temas).
4. Completar configuración OAuth de YouTube y probar subida real en modo
   privado (esto debe hacerse en máquina local, no en este sandbox).
5. Cuando el flujo esté validado: activar subida automática a "unlisted" o
   "public" con programación de fecha de publicación.
6. Integrar con el resto del ecosistema (LabiaAPP usa Groq/Supabase en
   Replit; este proyecto de música es independiente pero mismo estilo de
   trabajo: dirigir agentes de IA en vez de programar directamente).

## Convenciones del proyecto
- Todo el código nuevo debe seguir el mismo patrón: módulo independiente y
  testeable en `src/`, con un bloque `if __name__ == "__main__"` para probar
  por CLI antes de integrarlo en `main.py`.
- ffmpeg puro para audio+vídeo (más rápido/estable que moviepy para renders
  largos); moviepy solo si se necesita algo que ffmpeg no resuelve bien.
- Nunca subir `config/client_secret.json` ni `config/token.json` a git
  (añadidos a .gitignore).
