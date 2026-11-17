#!/bin/bash
# Remove o servidor do Extrator Caramujo (agente, binário, config e estado).
# NÃO mexe nos arquivos baixados, nem no origens.jsonl em Music/@rideblan33.
PLIST="$HOME/Library/LaunchAgents/com.caramujo.servidor.plist"
launchctl bootout "gui/$(id -u)/com.caramujo.servidor" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "$HOME/.caramujo"
echo "Servidor removido. ffmpeg e deno continuam no Homebrew (tira à parte se quiser)."
