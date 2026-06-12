#!/usr/bin/env python3
"""
Servidor local do Extrator Caramujo.

A extensão do Chrome manda a URL do vídeo pra cá (localhost:8765). Quem baixa
e converte é o yt-dlp + ffmpeg, rodando na máquina do Bruno. Nada sai pra fora
além do próprio download do YouTube; o servidor só escuta em 127.0.0.1.

Endpoints:
  GET  /status                       -> diz se está vivo e se yt-dlp/ffmpeg existem
  POST /baixar  {url, formato, pasta} -> baixa (formato: "mp3" ou "mp4")

As pastas de destino vivem aqui embaixo, em DESTINOS. Pra mudar um caminho,
edita aqui e reinicia o servidor.
"""

import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8765

HOME = os.path.expanduser("~")

# Destino final de cada opção do popup. Editável.
DESTINOS = {
    "": os.path.join(HOME, "Downloads"),
    "Samples/": os.path.join(HOME, "Music", "@rideblan33", "Samples"),
    "Inspiracoes/": os.path.join(HOME, "Music", "@rideblan33", "Inspiration"),
}

# Só aceita pedido vindo da extensão do Chrome.
ORIGEM_OK = re.compile(r"^chrome-extension://", re.I)


def achar_exe(nome):
    """Procura o executável no PATH e nos lugares comuns de Homebrew/pip."""
    import shutil
    candidatos = [
        shutil.which(nome),            # respeita o PATH do processo
        f"/opt/homebrew/bin/{nome}",   # Apple Silicon (Homebrew)
        f"/usr/local/bin/{nome}",      # Intel (Homebrew)
        os.path.join(HOME, ".local", "bin", nome),  # pip --user
        f"/usr/bin/{nome}",
    ]
    for c in candidatos:
        if not c:
            continue
        # Só confirma que o binário existe e é executável. Não roda com flag
        # de versão porque yt-dlp quer "--version" e ffmpeg quer "-version";
        # confiar no returncode de uma flag errada dá falso negativo.
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


YTDLP = achar_exe("yt-dlp")
FFMPEG = achar_exe("ffmpeg")


def montar_comando(url, formato, destino):
    saida = os.path.join(destino, "%(title).120B.%(ext)s")
    base = [
        YTDLP,
        "--no-playlist",
        "--restrict-filenames",
        "-o", saida,
        "--newline",
    ]
    if FFMPEG:
        base += ["--ffmpeg-location", os.path.dirname(FFMPEG)]

    if formato == "mp3":
        base += [
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",   # melhor VBR
        ]
    else:  # mp4
        base += [
            # melhor vídeo + melhor áudio, remuxado pra mp4
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
        ]
    base.append(url)
    return base


def baixar(url, formato, pasta):
    if not YTDLP:
        return False, "yt-dlp não encontrado. Roda o instalar.sh do servidor."
    if formato == "mp4" and not FFMPEG:
        return False, "ffmpeg não encontrado (precisa dele pra juntar vídeo+áudio). Roda o instalar.sh."
    if formato == "mp3" and not FFMPEG:
        return False, "ffmpeg não encontrado (precisa dele pra gerar MP3). Roda o instalar.sh."

    destino = DESTINOS.get(pasta, DESTINOS[""])
    os.makedirs(destino, exist_ok=True)

    cmd = montar_comando(url, formato, destino)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "Demorou demais (mais de 30 min) e foi cancelado."
    if proc.returncode != 0:
        erro = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = erro[-1] if erro else "yt-dlp falhou sem mensagem."
        return False, "Falha no download: " + msg
    return True, destino


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silencioso

    def _cors(self):
        origem = self.headers.get("Origin", "")
        if ORIGEM_OK.match(origem):
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _json(self, code, obj):
        corpo = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self._json(200, {
                "ok": True,
                "ytdlp": bool(YTDLP),
                "ffmpeg": bool(FFMPEG),
            })
        else:
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

    def do_POST(self):
        if self.path != "/baixar":
            self._json(404, {"ok": False, "erro": "rota desconhecida"})
            return
        try:
            tam = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tam) or b"{}")
        except Exception:
            self._json(400, {"ok": False, "erro": "corpo inválido"})
            return

        url = corpo.get("url", "")
        formato = corpo.get("formato", "mp3")
        pasta = corpo.get("pasta", "")
        if not url or formato not in ("mp3", "mp4"):
            self._json(400, {"ok": False, "erro": "faltou url ou formato inválido"})
            return

        ok, info = baixar(url, formato, pasta)
        if ok:
            self._json(200, {"ok": True, "pasta": info})
        else:
            self._json(500, {"ok": False, "erro": info})


def main():
    if not YTDLP:
        print("AVISO: yt-dlp não encontrado. Roda o instalar.sh primeiro.", file=sys.stderr)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Extrator Caramujo escutando em http://{HOST}:{PORT}")
    print(f"yt-dlp: {YTDLP or 'AUSENTE'} | ffmpeg: {FFMPEG or 'AUSENTE'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
