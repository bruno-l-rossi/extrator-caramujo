#!/bin/bash
# Instala o servidor do Extrator Caramujo (v4).
# Roda uma vez:  bash instalar.sh   (rodar de novo é seguro: serve pra atualizar o servidor)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.caramujo"
URL_YTDLP="https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp_macos"

echo "== Extrator Caramujo: instalando o servidor local =="

# 1) Homebrew só pra ffmpeg e deno
BREW="$(command -v brew || true)"
[ -z "$BREW" ] && [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew
[ -z "$BREW" ] && [ -x /usr/local/bin/brew ] && BREW=/usr/local/bin/brew
if [ -z "$BREW" ]; then
  echo "!! Homebrew não encontrado. Instala em https://brew.sh e roda este script de novo."
  exit 1
fi
for pkg in ffmpeg deno; do
  "$BREW" list --formula "$pkg" >/dev/null 2>&1 || { echo "-> instalando $pkg…"; "$BREW" install "$pkg"; }
done

# 2) yt-dlp nightly (binário oficial). O servidor se atualiza sozinho a partir daqui.
mkdir -p "$APP/bin"
echo "-> baixando o yt-dlp nightly…"
curl -fL --retry 3 -o "$APP/bin/yt-dlp.novo" "$URL_YTDLP"
chmod +x "$APP/bin/yt-dlp.novo"
xattr -d com.apple.quarantine "$APP/bin/yt-dlp.novo" 2>/dev/null || true
mv -f "$APP/bin/yt-dlp.novo" "$APP/bin/yt-dlp"
"$APP/bin/yt-dlp" --version

# 3) servidor + agente que sobe no login
cp "$DIR/servidor_caramujo.py" "$APP/servidor_caramujo.py"
PLIST="$HOME/Library/LaunchAgents/com.caramujo.servidor.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__HOME__#$HOME#g" "$DIR/com.caramujo.servidor.plist" > "$PLIST"
launchctl bootout "gui/$(id -u)/com.caramujo.servidor" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.caramujo.servidor" 2>/dev/null || true

# 4) confere
echo
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -s http://127.0.0.1:8765/status >/dev/null && break
  sleep 1
done
if curl -s http://127.0.0.1:8765/status >/dev/null; then
  curl -s http://127.0.0.1:8765/status | python3 -c 'import json,sys; d=json.load(sys.stdin); print("build", d["build"], "| yt-dlp", d["ytdlp_versao"], d["ytdlp_canal"], "| ffmpeg", d["ffmpeg"], "| js", d["js"])'
  echo "Servidor no ar. Quer ver ffmpeg True e js True."
  echo "Agora recarrega a extensão em chrome://extensions."
else
  echo "Servidor não respondeu. Olha o log:  tail -50 ~/.caramujo/servidor.log   (e ~/.caramujo/servidor.err)"
fi
