#!/bin/bash
# Instalador do servidor do Extrator Caramujo.
# Instala yt-dlp e ffmpeg, copia o servidor e sobe ele no login.
# Roda uma vez:  bash instalar.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== Extrator Caramujo: instalando o servidor local =="

# 1) ffmpeg via Homebrew (yt-dlp precisa dele pra MP3 e pra juntar vídeo+áudio)
if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/ffmpeg ] && [ ! -x /usr/local/bin/ffmpeg ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "-> instalando ffmpeg via Homebrew…"
    brew install ffmpeg
  else
    echo "!! Homebrew não encontrado. Instala o Homebrew (https://brew.sh) e roda de novo,"
    echo "   ou instala o ffmpeg manualmente. Sem ffmpeg o MP3 não funciona."
  fi
else
  echo "-> ffmpeg já presente."
fi

# 2) yt-dlp via pip (--user, não mexe no Python do sistema)
echo "-> instalando/atualizando yt-dlp…"
python3 -m pip install --user --upgrade yt-dlp --break-system-packages 2>/dev/null \
  || python3 -m pip install --user --upgrade yt-dlp

# 3) copia o servidor pra ~/.caramujo
mkdir -p "$HOME/.caramujo"
cp "$DIR/servidor_caramujo.py" "$HOME/.caramujo/servidor_caramujo.py"

# 4) cria as pastas de destino
mkdir -p "$HOME/Music/@rideblan33/Samples" "$HOME/Music/@rideblan33/Inspiration"

# 5) instala o agente que mantém o servidor no ar
mkdir -p "$HOME/Library/LaunchAgents"
cp "$DIR/com.caramujo.servidor.plist" "$HOME/Library/LaunchAgents/"
launchctl unload "$HOME/Library/LaunchAgents/com.caramujo.servidor.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.caramujo.servidor.plist"

sleep 2
echo
echo "== Pronto. Conferindo o servidor… =="
if curl -s http://127.0.0.1:8765/status >/dev/null; then
  curl -s http://127.0.0.1:8765/status
  echo
  echo "Servidor no ar. Agora é só usar a extensão no Chrome."
else
  echo "Servidor não respondeu ainda. Confere o log em ~/.caramujo/servidor.log"
fi
