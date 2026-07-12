#!/usr/bin/env bash
# Instalación automática (una sola vez).
# Uso: ./setup.sh
set -e

cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ATENCIÓN: no encuentro ffmpeg instalado."
  echo "  Mac:     brew install ffmpeg"
  echo "  Linux:   sudo apt install ffmpeg"
  echo "  Windows: descarga desde ffmpeg.org y añádelo al PATH"
  echo
fi

if [ ! -d venv ]; then
  echo "Creando entorno virtual..."
  python3 -m venv venv
fi

echo "Instalando dependencias..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "He creado .env a partir de .env.example."
  echo "Ábrelo con un editor de texto y pon tu ANTHROPIC_API_KEY antes de generar contenido."
else
  echo ".env ya existe, no lo toco."
fi

echo
echo "Instalación lista. A partir de ahora, para subir un tema nuevo:"
echo "  1. Copia el audio y la portada a la carpeta input/"
echo "  2. Ejecuta: venv/bin/python subir_tema.py"
echo "  3. Responde las preguntas y revisa el resultado en output/"
