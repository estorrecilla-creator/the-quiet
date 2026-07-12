# Contexto del proyecto — Automatización de contenido musical

## Qué es esto
Pipeline que automatiza TODO el proceso de publicación de una canción/LP en
YouTube, excepto la composición/producción musical (eso lo hace Salva).

Input: audio (mp3/wav) + portada (jpg/png)
Output: vídeo largo para YouTube + N Shorts + títulos/descripciones/hashtags,
todo en carpetas listas para revisión manual antes de subir.

## Estado actual (prototipo funcional, probado con audio sintético)
- `src/audio_analysis.py` — detecta mejores momentos (energía + onsets). FUNCIONA.
- `src/video_generator.py` — vídeo horizontal con waveform sobre portada. FUNCIONA.
- `src/shorts_generator.py` — shorts verticales 1080x1920 recortados de los
  mejores momentos, con fade in/out. FUNCIONA.
- `src/metadata_generator.py` — título/descripción/hashtags vía API de Claude
  (modelo `claude-sonnet-4-6`). Requiere ANTHROPIC_API_KEY. NO PROBADO EN VIVO
  (sin API key en el entorno de desarrollo).
- `src/youtube_uploader.py` — sube en modo PRIVADO vía OAuth. NO PROBADO
  (necesita client_secret.json de Google Cloud Console, no se puede generar
  automáticamente). Salva decidió: de momento NO integrar en el pipeline
  automático, dejar como módulo aparte hasta que se confirme el flujo.
- `main.py` — orquestador CLI que encadena todo.

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
1. Probar `metadata_generator.py` con ANTHROPIC_API_KEY real.
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
