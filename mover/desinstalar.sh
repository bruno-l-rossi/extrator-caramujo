#!/bin/bash
# Remove o mover do Extrator Caramujo.
launchctl unload "$HOME/Library/LaunchAgents/com.caramujo.mover.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.caramujo.mover.plist"
rm -rf "$HOME/.caramujo"
echo "Mover removido. As pastas e os arquivos ficam onde estão."
