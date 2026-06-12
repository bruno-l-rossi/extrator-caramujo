#!/bin/bash
# Remove o servidor do Extrator Caramujo.
launchctl unload "$HOME/Library/LaunchAgents/com.caramujo.servidor.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.caramujo.servidor.plist"
rm -rf "$HOME/.caramujo"
echo "Servidor removido. yt-dlp e ffmpeg continuam instalados (remove à parte se quiser)."
echo "Os arquivos já baixados em Music/@rideblan33 ficam onde estão."
