#!/bin/bash
# Instala o mover do Extrator Caramujo. Roda uma vez só:
#   bash instalar.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# Pastas de passagem (Downloads) e destinos finais (Music)
mkdir -p "$HOME/Downloads/Samples" "$HOME/Downloads/Inspiracoes"
mkdir -p "$HOME/Music/@rideblan33/Samples" "$HOME/Music/@rideblan33/Inspiration"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.caramujo"

cp "$DIR/mover-caramujo.sh" "$HOME/.caramujo/mover-caramujo.sh"
chmod +x "$HOME/.caramujo/mover-caramujo.sh"
cp "$DIR/com.caramujo.mover.plist" "$HOME/Library/LaunchAgents/"

launchctl unload "$HOME/Library/LaunchAgents/com.caramujo.mover.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.caramujo.mover.plist"

echo "Instalado. Tudo que cair em Downloads/Samples ou Downloads/Inspiracoes"
echo "vai automaticamente pra Music/@rideblan33 (Samples e Inspiration)."
