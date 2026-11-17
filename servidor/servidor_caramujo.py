#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor local do Extrator Caramujo (v4).

A extensão do Chrome manda a URL do vídeo pra cá (127.0.0.1:8765). Quem baixa e
converte é o yt-dlp + ffmpeg, rodando no Mac do Bruno. Só stdlib, Python 3.9+.

Rotas (todas JSON):
  GET  /status          versões, destinos, perfis, build
  GET  /progresso       {ativo, fila[], recentes[]}
  GET  /config          configuração atual
  POST /config          muda configuração (mescla com a atual)
  GET  /historico?n=20  últimos downloads (origens.jsonl)
  GET  /diagnostico     roda um teste real contra o YouTube e devolve o resumo
  POST /baixar          {url, perfil, destino?, titulo?, forcar?}  -> entra na fila
  POST /cancelar        {id}
  POST /mostrar         {id? | arquivo?}  abre o Finder
  POST /escolher_pasta  abre o seletor de pasta do macOS
  POST /atualizar       força atualização do yt-dlp

Perfis: sample (WAV), referencia (MP3), video (MP4 H.264 pra edição), video_max.
Arquivos em ~/.caramujo/: servidor_caramujo.py, servidor.log, estado.json,
config.json, bin/yt-dlp (binário nightly próprio). Em Music/@rideblan33/:
origens.jsonl (de onde veio cada arquivo).
"""

import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BUILD = "2026-11-16.1"
VERSAO_SERVIDOR = 4

HOST = "127.0.0.1"
PORT = 8765
HOME = os.path.expanduser("~")
PASTA_APP = os.environ.get("CARAMUJO_HOME") or os.path.join(HOME, ".caramujo")
PASTA_BIN = os.path.join(PASTA_APP, "bin")
BIN_PROPRIO = os.path.join(PASTA_BIN, "yt-dlp")
ARQ_LOG = os.path.join(PASTA_APP, "servidor.log")
ARQ_ESTADO = os.path.join(PASTA_APP, "estado.json")
ARQ_CONFIG = os.path.join(PASTA_APP, "config.json")
os.makedirs(PASTA_APP, exist_ok=True)

# ID fixo da extensão (vem da "key" do manifest.json). Só ela fala com o servidor.
EXTENSAO_ID = "iahhihnpbcmcjhmkcepiecadnppgienf"

URL_BIN_NIGHTLY = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp_macos"
URL_DIAGNOSTICO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", curto e estável

INTERVALO_UPDATE = 24 * 3600
RETRY_UPDATE = 30 * 60
LIMITE_SILENCIO = 180        # yt-dlp sem escrever nada por 3 min = travou
LIMITE_SILENCIO_CONV = 300   # ffmpeg convertendo demora mais sem escrever
LIMITE_TOTAL = 4 * 3600
VIGIA_INTERVALO = 5          # de quantos em quantos segundos o vigia confere o silêncio

PERFIS = {
    "sample": {"rotulo": "Sample", "tipo": "audio"},
    "referencia": {"rotulo": "Referência", "tipo": "audio"},
    "video": {"rotulo": "Vídeo", "tipo": "video"},
    "video_max": {"rotulo": "Vídeo máx.", "tipo": "video"},
}
COMPAT_FORMATO = {"mp3": "referencia", "mp4": "video_max"}

CONFIG_PADRAO = {
    "destinos": [
        {"id": "downloads", "rotulo": "Downloads", "caminho": "~/Downloads"},
        {"id": "samples", "rotulo": "Samples", "caminho": "~/Music/@rideblan33/Samples"},
        {"id": "inspiration", "rotulo": "Inspiration", "caminho": "~/Music/@rideblan33/Inspiration"},
    ],
    "perfil_destino": {
        "sample": "samples",
        "referencia": "inspiration",
        "video": "downloads",
        "video_max": "downloads",
    },
    "resolucao_max": 1080,          # 0 = sem limite (só vale pro perfil "video")
    "cookies": False,               # último degrau contra 403: login do navegador
    "navegador_cookies": "chrome",
    "clientes_alternativos": ["android_vr", "tv", "web_safari"],
    "arquivo_origens": "~/Music/@rideblan33/origens.jsonl",
    "extensoes_extras": [],
}
NAVEGADORES = ("chrome", "brave", "edge", "firefox", "safari")
RESOLUCOES = (0, 720, 1080, 1440, 2160)

CAMPOS_INFO = "%(.{id,title,channel,uploader,duration,webpage_url,filepath})j"
TPL_DL = ("download:CRMJ|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s"
          "|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|%(info.format_id)s"
          "|%(info.requested_formats.1.format_id|SINGLE)s|%(info.title)s")
TPL_PP = "postprocess:CRMJPP|%(progress.status)s|%(progress.postprocessor)s"

PP_ETAPAS = {
    "ExtractAudio": ("convertendo o áudio", 92),
    "Merger": ("juntando vídeo e áudio", 92),
    "VideoConvertor": ("convertendo o vídeo", 92),
    "Metadata": ("gravando os dados do arquivo", 97),
    "MoveFiles": ("movendo pra pasta", 99),
}

# ------------------------------------------------------------------- utilidades --

LOG_LOCK = threading.Lock()


def log(*partes):
    linha = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + " ".join(str(p) for p in partes)
    with LOG_LOCK:
        try:
            with open(ARQ_LOG, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            print(linha, flush=True)


def podar_log():
    """Passou de 2 MB, guarda só os últimos 200 KB (troca atômica do arquivo)."""
    try:
        if os.path.getsize(ARQ_LOG) <= 2 * 1024 * 1024:
            return
        with LOG_LOCK:
            with open(ARQ_LOG, "rb") as f:
                f.seek(-200 * 1024, 2)
                fim = f.read()
            tmp = ARQ_LOG + ".tmp"
            with open(tmp, "wb") as f:
                f.write(fim)
            os.replace(tmp, ARQ_LOG)
    except OSError:
        pass


def escrever_json(caminho, obj):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def ler_json(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


# ----------------------------------------------------------------------- estado --

ESTADO_LOCK = threading.Lock()


def carregar_estado():
    dados = ler_json(ARQ_ESTADO, {})
    return dados if isinstance(dados, dict) else {}


def atualizar_estado(**kw):
    with ESTADO_LOCK:
        e = carregar_estado()
        e.update(kw)
        try:
            escrever_json(ARQ_ESTADO, e)
        except OSError as ex:
            log("não consegui gravar estado.json:", ex)
        return e


# ----------------------------------------------------------------------- config --

def caminho_seguro(caminho):
    """Expande ~ e aceita só pasta dentro do HOME ou de /Volumes."""
    if not isinstance(caminho, str) or not caminho.strip():
        return None
    c = os.path.abspath(os.path.expanduser(caminho.strip()))
    if c == HOME or c.startswith(HOME + os.sep) or c.startswith("/Volumes/"):
        return c
    return None


def _config_base():
    cfg = json.loads(json.dumps(CONFIG_PADRAO))
    for d in cfg["destinos"]:
        d["caminho"] = os.path.abspath(os.path.expanduser(d["caminho"]))
    cfg["arquivo_origens"] = os.path.abspath(os.path.expanduser(cfg["arquivo_origens"]))
    return cfg


def validar_config(entrada):
    """Devolve (config_valida, lista_de_erros). Chave ausente fica no padrão."""
    cfg = _config_base()
    erros = []
    if not isinstance(entrada, dict):
        return cfg, ["a configuração precisa ser um objeto"]

    ds = entrada.get("destinos")
    if ds is not None:
        novos, ids = [], set()
        if not isinstance(ds, list) or not ds:
            erros.append("destinos precisa ser uma lista com pelo menos 1 pasta")
        else:
            for d in ds:
                if not isinstance(d, dict):
                    erros.append("destino inválido")
                    continue
                i = d.get("id")
                rotulo = str(d.get("rotulo") or "").strip()[:40]
                c = caminho_seguro(d.get("caminho"))
                if not isinstance(i, str) or not re.fullmatch(r"[a-z0-9_-]{1,30}", i) or i in ids:
                    erros.append("destino com id inválido ou repetido: %r" % (i,))
                    continue
                if not c:
                    erros.append("a pasta de '%s' precisa ficar dentro do teu usuário (ou em /Volumes)" % (rotulo or i))
                    continue
                ids.add(i)
                novos.append({"id": i, "rotulo": rotulo or i, "caminho": c})
        if novos and not erros:
            cfg["destinos"] = novos

    ids = [d["id"] for d in cfg["destinos"]]
    pd = entrada.get("perfil_destino")
    if isinstance(pd, dict):
        for k, v in pd.items():
            if k in PERFIS and v in ids:
                cfg["perfil_destino"][k] = v
            else:
                erros.append("perfil %r com destino inexistente %r" % (k, v))
    for k in PERFIS:
        if cfg["perfil_destino"].get(k) not in ids:
            cfg["perfil_destino"][k] = ids[0]

    if "resolucao_max" in entrada:
        if entrada["resolucao_max"] in RESOLUCOES:
            cfg["resolucao_max"] = entrada["resolucao_max"]
        else:
            erros.append("resolucao_max precisa ser uma de %s" % (RESOLUCOES,))
    if "cookies" in entrada:
        if isinstance(entrada["cookies"], bool):
            cfg["cookies"] = entrada["cookies"]
        else:
            erros.append("cookies precisa ser verdadeiro ou falso")
    if "navegador_cookies" in entrada:
        if entrada["navegador_cookies"] in NAVEGADORES:
            cfg["navegador_cookies"] = entrada["navegador_cookies"]
        else:
            erros.append("navegador_cookies precisa ser um de %s" % (NAVEGADORES,))
    cl = entrada.get("clientes_alternativos")
    if cl is not None:
        if isinstance(cl, list) and len(cl) <= 6 and all(isinstance(x, str) and re.fullmatch(r"[a-z_]{2,20}", x) for x in cl):
            cfg["clientes_alternativos"] = cl
        else:
            erros.append("clientes_alternativos inválido")
    ex = entrada.get("extensoes_extras")
    if ex is not None:
        if isinstance(ex, list) and all(isinstance(x, str) and re.fullmatch(r"[a-p]{32}", x) for x in ex):
            cfg["extensoes_extras"] = ex
        else:
            erros.append("extensoes_extras inválido")
    if "arquivo_origens" in entrada:
        c = caminho_seguro(entrada["arquivo_origens"])
        if c:
            cfg["arquivo_origens"] = c
        else:
            erros.append("arquivo_origens fora do teu usuário")
    return cfg, erros


def carregar_config():
    cfg, _ = validar_config(ler_json(ARQ_CONFIG, {}))
    return cfg


def salvar_config(cfg):
    escrever_json(ARQ_CONFIG, cfg)


def destino_por_id(cfg, destino_id):
    for d in cfg["destinos"]:
        if d["id"] == destino_id:
            return d
    return cfg["destinos"][0]


def caminho_permitido(arquivo, cfg):
    """Só deixa abrir no Finder o que está dentro de algum destino configurado."""
    try:
        real = os.path.realpath(arquivo)
        for d in cfg["destinos"]:
            base = os.path.realpath(d["caminho"])
            if real == base or real.startswith(base + os.sep):
                return True
    except OSError:
        pass
    return False


# ------------------------------------------------------------------ ferramentas --

def achar_exe(nome):
    """yt-dlp: o binário nightly próprio vem primeiro. Depois Homebrew (Apple Silicon,
    Intel), PATH, deno, sistema. O ~/.local/bin (pip da v2) fica por último."""
    candidatos = []
    if nome == "yt-dlp":
        candidatos.append(BIN_PROPRIO)
    candidatos += [
        "/opt/homebrew/bin/" + nome,
        "/usr/local/bin/" + nome,
        shutil.which(nome),
        os.path.join(HOME, ".deno", "bin", nome),
        "/usr/bin/" + nome,
        os.path.join(HOME, ".local", "bin", nome),
    ]
    for c in candidatos:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


class Ferramentas:
    def __init__(self):
        self.recarregar()

    def recarregar(self):
        self.ytdlp = achar_exe("yt-dlp")
        self.ffmpeg = achar_exe("ffmpeg")
        self.deno = achar_exe("deno")
        self.node = achar_exe("node")
        self.brew = achar_exe("brew")
        self.versao = self._versao()

    @property
    def proprio(self):
        return bool(self.ytdlp) and self.ytdlp == BIN_PROPRIO

    @property
    def origem(self):
        if not self.ytdlp:
            return None
        if self.proprio:
            return "proprio"
        if self.ytdlp.startswith(("/opt/homebrew/", "/usr/local/")):
            return "brew"
        return "outro"

    @property
    def canal(self):
        if not self.versao:
            return None
        return "nightly" if self.versao.count(".") >= 3 else "stable"

    def _versao(self):
        if not self.ytdlp:
            return None
        try:
            r = subprocess.run([self.ytdlp, "--version"], capture_output=True, text=True, timeout=60)
            return r.stdout.strip() or None
        except Exception:
            return None


FER = Ferramentas()

TRAVA_YTDLP = threading.Lock()      # nunca atualiza no meio de um download, nem o contrário
ATUALIZANDO = threading.Event()


def baixar_binario_proprio():
    """Baixa o yt-dlp nightly (binário oficial universal do macOS) pra ~/.caramujo/bin."""
    if sys.platform != "darwin":
        return False
    tmp = BIN_PROPRIO + ".novo"
    try:
        os.makedirs(PASTA_BIN, exist_ok=True)
        req = urllib.request.Request(URL_BIN_NIGHTLY, headers={"User-Agent": "extrator-caramujo"})
        with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.chmod(tmp, 0o755)
        subprocess.run(["xattr", "-d", "com.apple.quarantine", tmp], capture_output=True)
        v = subprocess.run([tmp, "--version"], capture_output=True, text=True, timeout=90)
        if v.returncode != 0 or not v.stdout.strip():
            raise RuntimeError("binário baixado não roda: " + (v.stderr or "")[-200:])
        os.replace(tmp, BIN_PROPRIO)
        log("binário próprio do yt-dlp instalado:", v.stdout.strip())
        return True
    except Exception as e:
        log("não consegui baixar o binário do yt-dlp:", e)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _rodar_update(cmd):
    log("  ", " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        saida = (r.stdout + r.stderr).strip().splitlines()
        if saida:
            log("  ", saida[-1])
        return r.returncode == 0
    except Exception as e:
        log("   update falhou:", e)
        return False


def atualizar_ytdlp(motivo):
    """Atualiza o yt-dlp. Devolve True se a versão mudou. Só adia o próximo update
    de 24 h se deu certo; se falhou (rede ainda subindo no login, por ex.), tenta
    de novo em 30 min."""
    ATUALIZANDO.set()
    antes = FER.versao
    ok = False
    agora = time.time()
    try:
        atualizar_estado(ultima_tentativa_update=agora)
        log("update do yt-dlp (%s)" % motivo)
        if not FER.proprio and sys.platform == "darwin" and baixar_binario_proprio():
            ok = True
        elif FER.proprio:
            ok = _rodar_update([FER.ytdlp, "--update-to", "nightly"])
        elif FER.ytdlp and FER.brew and os.path.dirname(FER.ytdlp) == os.path.dirname(FER.brew):
            ok = _rodar_update([FER.brew, "upgrade", "yt-dlp"])
        FER.recarregar()
    finally:
        ATUALIZANDO.clear()
    agora = time.time()
    if ok:
        atualizar_estado(ultimo_update_ok=agora, proximo_update=agora + INTERVALO_UPDATE)
    else:
        atualizar_estado(proximo_update=agora + RETRY_UPDATE)
    log("   yt-dlp %s -> %s (%s)" % (antes, FER.versao, "ok" if ok else "falhou"))
    return FER.versao != antes


def loop_update():
    while True:
        try:
            podar_log()
            if time.time() >= carregar_estado().get("proximo_update", 0):
                with TRAVA_YTDLP:
                    atualizar_ytdlp("rotina")
        except Exception as e:
            log("loop_update:", repr(e))
        time.sleep(300)


# ------------------------------------------------------------------ erros do yt-dlp --

# (nome, regex, final, texto, acao). final=None decide por config (ver classificar_erro).
_ERROS = [
    ("disco", r"No space left on device|\[Errno 28\]", True,
     "O disco está cheio. Libera espaço e tenta de novo.", "tentar"),
    ("rede", r"nodename nor servname|Network is unreachable|Temporary failure in name resolution|"
             r"Name or service not known|No route to host|getaddrinfo failed|Connection refused|"
             r"urlopen error \[Errno (8|51|60|61|65)\]", True,
     "Sem conexão com a internet. Confere a rede e tenta de novo.", "tentar"),
    ("privado", r"Private video|members-only|Join this channel|Members-only", True,
     "Vídeo privado ou só pra membros do canal.", None),
    ("live", r"live event will begin|Premieres in|live stream recording is not available", True,
     "Essa live ou estreia ainda não terminou. Tenta de novo quando acabar.", "tentar"),
    ("indisponivel", r"Video unavailable|has been removed|no longer available|video is not available|"
                     r"has been terminated|blocked it in your country|not made this video available|"
                     r"This video is unavailable", True,
     "Vídeo indisponível (removido, bloqueado no teu país ou ainda não liberado).", None),
    ("idade", r"age[- ]restricted|confirm your age|inappropriate for some users", None,
     "Vídeo com restrição de idade. Só baixa com o login do Chrome ligado nas opções.", "cookies"),
    ("bot", r"Sign in to confirm|not a bot", False,
     "O YouTube pediu login pra provar que não é robô. Liga o login do Chrome nas opções.", "cookies"),
    ("403", r"HTTP Error 403|Forbidden", False,
     "O YouTube recusou o download (403) depois de atualizar o yt-dlp e tentar outros caminhos. "
     "Tenta de novo em alguns minutos.", "cookies"),
    ("travou", r"travou sem resposta|demorou demais", False,
     "O download travou (sem resposta) e foi parado. Tenta de novo.", "tentar"),
    ("timeout", r"timed out|Read timeout", False,
     "A conexão com o YouTube ficou lenta demais e foi cortada. Tenta de novo.", "tentar"),
    ("extracao", r"Unable to extract|nsig|signature|player response|PO Token|n challenge|"
                 r"Requested format is not available|Precondition", False,
     "O yt-dlp não conseguiu ler esse vídeo (o YouTube mudou algo). Tenta de novo; se repetir, roda o diagnóstico.",
     "diagnostico"),
]


def classificar_erro(linhas, cfg=None):
    """Lê a saída do yt-dlp e devolve {nome, texto, acao, final}.
    final=True: não adianta tentar outro caminho."""
    cfg = cfg or {}
    linhas = [str(l) for l in linhas]
    erros = [l for l in linhas if "ERROR" in l]
    for texto in ("\n".join(erros), "\n".join(linhas)):
        if not texto.strip():
            continue
        for nome, rx, final, msg, acao in _ERROS:
            if re.search(rx, texto, re.I):
                if final is None:
                    final = not cfg.get("cookies")
                if nome == "403" and cfg.get("cookies"):
                    acao = "tentar"
                return {"nome": nome, "texto": msg, "acao": acao, "final": bool(final)}
    bruto = (erros or linhas or ["yt-dlp falhou sem mensagem."])[-1]
    bruto = re.sub(r"^ERROR:\s*", "", bruto).strip()[:300]
    return {"nome": "desconhecido", "texto": "Falha no download: " + bruto, "acao": "tentar", "final": False}


def erro_amigavel(linhas, cfg=None):
    return classificar_erro(linhas, cfg)["texto"]


# ---------------------------------------------------------------------- progresso --

def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_progress(linha):
    """Lê as linhas CRMJ|... e CRMJPP|... que o yt-dlp imprime (templates acima)."""
    if linha.startswith("CRMJPP|"):
        p = linha.split("|")
        return {"tipo": "pp", "status": p[1] if len(p) > 1 else "", "pp": p[2] if len(p) > 2 else ""}
    if linha.startswith("CRMJ|"):
        p = linha.split("|", 9)
        if len(p) < 10:
            return None
        _, status, baixado, total, estimado, vel, eta, fid, seg, titulo = p
        return {
            "tipo": "dl", "status": status, "baixado": _num(baixado),
            "total": _num(total) or _num(estimado), "vel": _num(vel), "eta": _num(eta),
            "formato": fid, "unico": seg == "SINGLE", "titulo": titulo,
        }
    return None


class Progresso:
    """Junta a % de cada stream (vídeo, áudio) numa barra só, de 0 a 90.
    O resto (conversão, metadados, mover) completa até 100. Nunca anda pra trás."""

    def __init__(self, tipo):
        self.tipo = tipo
        self.esperadas = 2 if tipo == "video" else 1
        self.vistos = []
        self.ultimo = 0.0

    def atualizar(self, p):
        fid = p["formato"]
        if fid not in self.vistos:
            self.vistos.append(fid)
        if p["unico"]:
            self.esperadas = 1
        n = max(self.esperadas, len(self.vistos))
        idx = self.vistos.index(fid)
        if p["status"] == "finished":
            frac = 1.0
        elif p["total"]:
            frac = min(1.0, (p["baixado"] or 0) / p["total"])
        else:
            frac = 0.0
        pct = max(self.ultimo, (idx + frac) / n * 90.0)
        self.ultimo = pct
        etapa = "áudio" if self.tipo == "audio" else ("vídeo" if idx == 0 else "áudio")
        return {"pct": round(pct, 1), "etapa": etapa, "velocidade": p["vel"], "eta": p["eta"]}


# ------------------------------------------------------------------------ comando --

def flags_youtube():
    """Runtime JS (desafio do player) e ffmpeg. Vale pra download e diagnóstico."""
    f = []
    if FER.versao and FER.versao >= "2025.11":
        if FER.deno:
            f += ["--js-runtimes", "deno:" + FER.deno]
        elif FER.node:
            f += ["--js-runtimes", "node:" + FER.node]
        f += ["--remote-components", "ejs:github"]
    if FER.ffmpeg:
        f += ["--ffmpeg-location", os.path.dirname(FER.ffmpeg)]
    return f


def args_perfil(perfil, cfg):
    if perfil == "sample":
        # WAV direto da melhor faixa de áudio: 1 decodificação, sem MP3 no meio.
        return ["-f", "ba/b", "-x", "--audio-format", "wav"]
    if perfil == "referencia":
        return ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "2"]
    if perfil == "video":
        res = cfg.get("resolucao_max") or 0
        ordem = ("vcodec:h264,res:%d,acodec:m4a" % res) if res else "vcodec:h264,acodec:m4a"
        return ["-S", ordem, "--merge-output-format", "mp4"]
    return ["-f", "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b", "--merge-output-format", "mp4"]  # video_max


def montar_comando(url, perfil, destino, passo_args, arq_info, cfg):
    cmd = [
        FER.ytdlp, "--ignore-config",
        "--no-playlist", "--no-mtime",
        "--windows-filenames", "--trim-filenames", "180",
        "-o", os.path.join(destino, "%(title).150B.%(ext)s"),
        "--newline", "--embed-metadata",
        "--progress-template", TPL_DL,
        "--progress-template", TPL_PP,
        "--print-to-file", "after_move:" + CAMPOS_INFO, arq_info,
        "--retries", "10", "--fragment-retries", "10", "--extractor-retries", "3",
        "--retry-sleep", "http:exp=1:20",
        "--concurrent-fragments", "4", "--socket-timeout", "30",
    ]
    cmd += flags_youtube()
    cmd += args_perfil(perfil, cfg)
    cmd += passo_args
    cmd.append(url)
    return cmd


def montar_escada(cfg, estado):
    """Lista de tentativas, da mais barata à mais pesada. A que venceu nas últimas
    24 h vai pra frente."""
    passos = [
        {"nome": "padrão", "args": []},
        {"nome": "sem cache", "args": ["--no-cache-dir"]},
        {"nome": "yt-dlp novo", "args": ["--no-cache-dir"], "update": True},
    ]
    for c in cfg.get("clientes_alternativos", []):
        passos.append({"nome": "cliente " + c,
                       "args": ["--no-cache-dir", "--extractor-args", "youtube:player_client=" + c]})
    passos.append({"nome": "IPv4", "args": ["--no-cache-dir", "--force-ipv4"]})
    if cfg.get("cookies"):
        passos.append({"nome": "login do navegador",
                       "args": ["--no-cache-dir", "--cookies-from-browser", cfg.get("navegador_cookies", "chrome")]})
    v = estado.get("vencedora")
    if isinstance(v, dict) and time.time() - v.get("quando", 0) < 86400:
        for p in passos:
            if p["nome"] == v.get("nome") and not p.get("update"):
                passos.remove(p)
                passos.insert(0, p)
                break
    return passos


# ------------------------------------------------------------------ origem e duplicado --

def extrair_id(url):
    try:
        u = urlparse(url)
    except Exception:
        return None
    h = (u.hostname or "").lower()
    vid = None
    if h == "youtu.be":
        vid = u.path[1:12]
    elif h in ("youtube.com", "youtube-nocookie.com") or h.endswith((".youtube.com", ".youtube-nocookie.com")):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(shorts|live|embed)/([\w-]{11})", u.path)
            if m:
                vid = m.group(2)
    return vid if vid and re.fullmatch(r"[\w-]{11}", vid) else None


def registrar_origem(cfg, entrada):
    try:
        os.makedirs(os.path.dirname(cfg["arquivo_origens"]), exist_ok=True)
        with open(cfg["arquivo_origens"], "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except OSError as e:
        log("não consegui gravar origens.jsonl:", e)


def _linhas_origens(cfg):
    try:
        with open(cfg["arquivo_origens"], encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except OSError:
        return
    for l in reversed(linhas):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if isinstance(e, dict):
            yield e


def ja_baixado(cfg, id_video, perfil, destino):
    for e in _linhas_origens(cfg):
        if (e.get("id_video") == id_video and e.get("perfil") == perfil and e.get("destino") == destino
                and e.get("arquivo") and os.path.isfile(e["arquivo"])):
            return e
    return None


def historico(cfg, n=20):
    itens = []
    for e in _linhas_origens(cfg):
        e = dict(e)
        e["existe"] = bool(e.get("arquivo")) and os.path.isfile(e["arquivo"])
        itens.append(e)
        if len(itens) >= n:
            break
    return itens


def marcar_origem_finder(arquivo, url):
    """Preenche o campo 'De onde veio' do Finder (só macOS)."""
    if sys.platform != "darwin":
        return
    try:
        dados = plistlib.dumps([url], fmt=plistlib.FMT_BINARY)
        subprocess.run(["xattr", "-wx", "com.apple.metadata:kMDItemWhereFroms", dados.hex(), arquivo],
                       capture_output=True, timeout=15)
    except Exception as e:
        log("xattr falhou:", e)


RE_PARCIAL = re.compile(r"(\.part(-Frag\d+)?|\.ytdl|\.temp(\.[A-Za-z0-9]+)?|"
                        r"\.f\d+(-\w+)?\.[a-z0-9]{2,4}(\.part|\.ytdl)?)$")


def limpar_parciais(destino, desde):
    """Apaga restos de download (.part, .ytdl, .f251.webm...) criados a partir de `desde`."""
    n = 0
    try:
        nomes = os.listdir(destino)
    except OSError:
        return 0
    for nome in nomes:
        if not RE_PARCIAL.search(nome):
            continue
        p = os.path.join(destino, nome)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) >= desde - 5:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


def mais_novo(destino, desde):
    achado, melhor = None, 0
    try:
        for nome in os.listdir(destino):
            p = os.path.join(destino, nome)
            if os.path.isfile(p) and not RE_PARCIAL.search(nome):
                m = os.path.getmtime(p)
                if m >= desde - 2 and m > melhor:
                    achado, melhor = p, m
    except OSError:
        pass
    return achado


# --------------------------------------------------------------------- job e fila --

_ID_LOCK = threading.Lock()
_ULTIMO_ID = [0]


def novo_id():
    with _ID_LOCK:
        _ULTIMO_ID[0] = max(_ULTIMO_ID[0] + 1, int(time.time() * 1000))
        return _ULTIMO_ID[0]


class Job:
    CAMPOS = ("id", "url", "video_id", "perfil", "destino", "titulo", "estado", "pct", "etapa",
              "velocidade", "eta", "tentativa", "estrategia", "texto", "acao", "arquivo",
              "pasta", "inicio", "fim")

    def __init__(self, url, perfil, destino, titulo="", id=None):
        self.id = id or novo_id()
        self.url = url
        self.video_id = extrair_id(url)
        self.perfil = perfil
        self.destino = destino
        self.titulo = titulo or ""
        self.estado = "na_fila"
        self.pct = 0
        self.etapa = ""
        self.velocidade = None
        self.eta = None
        self.tentativa = 0
        self.estrategia = ""
        self.texto = ""
        self.acao = None
        self.arquivo = None
        self.pasta = None
        self.inicio = None
        self.fim = None
        self.proc = None
        self.cancelado = False

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def publico(self):
        return {k: getattr(self, k) for k in self.CAMPOS}

    def resumo(self):
        return {"id": self.id, "url": self.url, "perfil": self.perfil, "destino": self.destino,
                "titulo": self.titulo, "pasta": self.pasta, "inicio": self.inicio}


class Fila:
    def __init__(self):
        self.cond = threading.Condition()
        self.pendentes = []
        self.ativo = None
        self.recentes = []

    def _persistir(self):
        atualizar_estado(
            fila=[j.resumo() for j in self.pendentes],
            ativo=self.ativo.resumo() if self.ativo else None,
            recentes=self.recentes,
        )

    def adicionar(self, job):
        with self.cond:
            self.pendentes.append(job)
            pos = len(self.pendentes) - 1 + (1 if self.ativo else 0)
            self._persistir()
            self.cond.notify()
            return pos

    def proximo(self):
        with self.cond:
            while not self.pendentes:
                self.cond.wait()
            job = self.pendentes.pop(0)
            self.ativo = job
            job.set(estado="preparando", inicio=time.time())
            self._persistir()
            return job

    def concluir(self, job):
        with self.cond:
            self.ativo = None
            self.recentes.insert(0, job.publico())
            del self.recentes[10:]
            self._persistir()

    def cancelar(self, id_job):
        with self.cond:
            if self.ativo and self.ativo.id == id_job:
                self.ativo.cancelado = True
                if self.ativo.proc:
                    matar(self.ativo.proc)
                return True
            for j in self.pendentes:
                if j.id == id_job:
                    self.pendentes.remove(j)
                    j.set(estado="cancelado", texto="Cancelado.", fim=time.time())
                    self.recentes.insert(0, j.publico())
                    del self.recentes[10:]
                    self._persistir()
                    return True
        return False

    def achar(self, id_job):
        with self.cond:
            if self.ativo and self.ativo.id == id_job:
                return self.ativo.publico()
            for j in self.pendentes:
                if j.id == id_job:
                    return j.publico()
            for r in self.recentes:
                if r.get("id") == id_job:
                    return dict(r)
        return None

    def repetido(self, video_id, perfil, destino):
        with self.cond:
            for j in ([self.ativo] if self.ativo else []) + self.pendentes:
                if j.video_id == video_id and j.perfil == perfil and j.destino == destino:
                    return j.id
        return None

    def snapshot(self):
        with self.cond:
            return {
                "ok": True, "build": BUILD,
                "ativo": self.ativo.publico() if self.ativo else None,
                "fila": [j.publico() for j in self.pendentes],
                "recentes": [dict(r) for r in self.recentes],
            }


FILA = Fila()


def matar(proc):
    """Encerra o yt-dlp e tudo que ele abriu (ffmpeg). SIGTERM, depois SIGKILL."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass

    def _forcar():
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    t = threading.Timer(5, _forcar)
    t.daemon = True
    t.start()


def _tratar_linha(job, prog, linha):
    p = parse_progress(linha)
    if not p:
        return
    if p["tipo"] == "dl":
        job.set(estado="baixando", **prog.atualizar(p))
        if p["titulo"] and p["titulo"] != "NA":
            job.titulo = p["titulo"]
    elif p["status"] == "started":
        nome, pct = PP_ETAPAS.get(p["pp"], ("finalizando", 96))
        job.set(estado="convertendo", etapa=nome, pct=max(job.pct or 0, pct), velocidade=None, eta=None)


def rodar_ytdlp(job, cmd, tipo):
    """Roda o yt-dlp lendo a saída linha a linha. Devolve (código, últimas_linhas)."""
    prog = Progresso(tipo)
    cauda = deque(maxlen=40)
    inicio = time.time()
    sinal = [inicio]
    motivo = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                bufsize=1, errors="replace", start_new_session=True)
    except OSError as e:
        return -1, ["ERROR: não consegui iniciar o yt-dlp: %s" % e]
    job.proc = proc
    parar = threading.Event()

    def vigia():
        while not parar.wait(VIGIA_INTERVALO):
            limite = LIMITE_SILENCIO_CONV if job.estado == "convertendo" else LIMITE_SILENCIO
            agora = time.time()
            if agora - sinal[0] > limite:
                motivo.append("travou")
                matar(proc)
                return
            if agora - inicio > LIMITE_TOTAL:
                motivo.append("total")
                matar(proc)
                return

    threading.Thread(target=vigia, daemon=True).start()
    try:
        for linha in proc.stdout:
            sinal[0] = time.time()
            linha = linha.rstrip("\n")
            if not linha:
                continue
            if linha.startswith("CRMJ"):
                _tratar_linha(job, prog, linha)
            else:
                cauda.append(linha)
        proc.wait()
    finally:
        parar.set()
        job.proc = None
    if motivo:
        cauda.append("ERROR: travou sem resposta" if motivo[0] == "travou" else "ERROR: demorou demais e foi parado")
    return proc.returncode, list(cauda)


def _sucesso(job, cfg, destino, passo, arq_info, inicio):
    info = ler_json(arq_info, None)
    if not isinstance(info, dict):
        # --print-to-file grava 1 JSON por linha; pega a última
        info = {}
        try:
            with open(arq_info, encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        info = json.loads(l)
        except (OSError, ValueError):
            pass
    arquivo = info.get("filepath")
    if not arquivo or not os.path.isfile(arquivo):
        arquivo = mais_novo(destino, inicio)
    titulo = info.get("title") or job.titulo
    rotulo = destino_por_id(cfg, job.destino)["rotulo"]
    if arquivo:
        registrar_origem(cfg, {
            "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "id_video": job.video_id, "url": job.url, "titulo": titulo,
            "canal": info.get("channel") or info.get("uploader"), "duracao": info.get("duration"),
            "perfil": job.perfil, "destino": job.destino, "arquivo": arquivo, "estrategia": passo["nome"],
        })
        marcar_origem_finder(arquivo, job.url)
    if passo["nome"] == "padrão":
        atualizar_estado(vencedora=None)
    elif not passo.get("update"):
        atualizar_estado(vencedora={"nome": passo["nome"], "quando": time.time()})
    job.set(estado="ok", pct=100, fim=time.time(), arquivo=arquivo, titulo=titulo, acao=None,
            velocidade=None, eta=None, etapa="", texto="Pronto. Salvo em %s." % rotulo)
    try:
        mb = os.path.getsize(arquivo) / 1048576.0 if arquivo else 0
    except OSError:
        mb = 0
    log("ok: perfil=%s via '%s' em %ds, %.1f MB -> %s" % (job.perfil, passo["nome"], time.time() - inicio, mb, arquivo))


def _rodar_escada(job, cfg, destino, tipo):
    inicio = job.inicio or time.time()
    arq_info = os.path.join(PASTA_APP, "info_%d.json" % job.id)
    passos = montar_escada(cfg, carregar_estado())
    ultimas, travou, cls = [], 0, None
    try:
        for i, passo in enumerate(passos):
            if job.cancelado:
                break
            if passo.get("update"):
                if time.time() - carregar_estado().get("ultima_tentativa_update", 0) < 3600:
                    continue  # já atualizou faz pouco, repetir não muda nada
                job.set(estado="atualizando", pct=0, etapa="YouTube recusou. Atualizando o yt-dlp e tentando de novo…")
                atualizar_ytdlp("falha no download")
            if not FER.ytdlp:
                cls = {"texto": "yt-dlp não encontrado. Roda o instalar.sh do servidor.", "acao": "instalar"}
                break
            job.set(estado="preparando", pct=0, etapa="", tentativa=i + 1, estrategia=passo["nome"],
                    velocidade=None, eta=None)
            try:
                os.remove(arq_info)
            except OSError:
                pass
            cmd = montar_comando(job.url, job.perfil, destino, passo["args"], arq_info, cfg)
            log("tentativa %d (%s) %s %s" % (i + 1, passo["nome"], job.perfil, job.url))
            codigo, ultimas = rodar_ytdlp(job, cmd, tipo)
            if job.cancelado:
                break
            if codigo == 0:
                _sucesso(job, cfg, destino, passo, arq_info, inicio)
                return
            cls = classificar_erro(ultimas, cfg)
            log("falhou (código %s, classe %s):" % (codigo, cls["nome"]))
            for l in ultimas[-8:]:
                log("   ", l)
            if cls["nome"] == "travou":
                travou += 1
            if cls["final"] or travou >= 2:
                break
        limpar_parciais(destino, inicio)
        if job.cancelado:
            job.set(estado="cancelado", texto="Cancelado.", acao=None, fim=time.time(), velocidade=None, eta=None)
        else:
            cls = cls or {"texto": "Falhou sem mensagem. Roda o diagnóstico.", "acao": "diagnostico"}
            job.set(estado="erro", texto=cls["texto"], acao=cls["acao"], fim=time.time(), velocidade=None, eta=None)
    finally:
        try:
            os.remove(arq_info)
        except OSError:
            pass


def executar_job(job):
    cfg = carregar_config()
    dest = destino_por_id(cfg, job.destino)
    destino = dest["caminho"]
    os.makedirs(destino, exist_ok=True)
    job.set(pasta=destino)
    if ATUALIZANDO.is_set():
        job.set(estado="atualizando", pct=0, etapa="Atualizando o yt-dlp antes de baixar…")
    with TRAVA_YTDLP:
        _rodar_escada(job, cfg, destino, PERFIS[job.perfil]["tipo"])


def loop_worker():
    while True:
        job = FILA.proximo()
        try:
            executar_job(job)
        except Exception as e:
            log("erro inesperado no job %s: %r" % (job.id, e))
            if job.estado not in ("ok", "cancelado"):
                job.set(estado="erro", texto="Erro interno do servidor: %s" % e, acao="diagnostico", fim=time.time())
        finally:
            FILA.concluir(job)


def retomar():
    """Depois de um restart: o job que estava rodando vira erro (com limpeza dos
    restos), e a fila que sobrou continua."""
    est = carregar_estado()
    FILA.recentes = [r for r in est.get("recentes", []) if isinstance(r, dict)][:10]
    ativo = est.get("ativo")
    if isinstance(ativo, dict) and ativo.get("url") and ativo.get("perfil") in PERFIS:
        if ativo.get("pasta"):
            limpar_parciais(ativo["pasta"], ativo.get("inicio") or 0)
        j = Job(ativo["url"], ativo["perfil"], ativo.get("destino"), ativo.get("titulo"), id=ativo.get("id"))
        j.set(estado="erro", fim=time.time(), acao="tentar",
              texto="O servidor reiniciou no meio do download. Baixa de novo.")
        FILA.recentes.insert(0, j.publico())
        del FILA.recentes[10:]
    for m in est.get("fila", []):
        if isinstance(m, dict) and m.get("url") and m.get("perfil") in PERFIS:
            FILA.adicionar(Job(m["url"], m["perfil"], m.get("destino"), m.get("titulo"), id=m.get("id")))
    atualizar_estado(ativo=None, recentes=FILA.recentes)


# ------------------------------------------------------------------ diagnóstico e mac --

def diagnostico():
    cfg = carregar_config()
    js = os.path.basename(FER.deno) if FER.deno else (os.path.basename(FER.node) if FER.node else "AUSENTE")
    est = carregar_estado()
    linhas = [
        "build %s | yt-dlp %s (%s, %s) | ffmpeg %s | js %s" % (
            BUILD, FER.versao or "AUSENTE", FER.origem or "-", FER.canal or "-",
            "ok" if FER.ffmpeg else "AUSENTE", js),
        "último update ok: %s | vencedora: %s" % (
            datetime.fromtimestamp(est["ultimo_update_ok"]).strftime("%Y-%m-%d %H:%M") if est.get("ultimo_update_ok") else "nunca",
            (est.get("vencedora") or {}).get("nome", "padrão")),
        "login do navegador: %s" % ("ligado" if cfg.get("cookies") else "desligado"),
    ]
    if not FER.ytdlp:
        return {"ok": False, "resumo": "yt-dlp não encontrado. Roda o instalar.sh.", "linhas": linhas}
    cmd = [FER.ytdlp, "--ignore-config", "-v", "--simulate", "--no-playlist", "-f", "ba"] + flags_youtube() + [URL_DIAGNOSTICO]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "resumo": "O teste passou de 2 minutos sem responder.", "linhas": linhas}
    saida = (r.stdout + "\n" + r.stderr).splitlines()
    chaves = ("yt-dlp version", "JS runtimes", "JS Challenge", "PO Token Providers", "Request Handlers",
              "WARNING", "ERROR", "Python")
    linhas += [l[:200] for l in saida if any(k in l for k in chaves)][:30]
    if r.returncode == 0:
        return {"ok": True, "resumo": "Tudo certo: o yt-dlp leu um vídeo de teste do YouTube.", "linhas": linhas}
    return {"ok": False, "resumo": classificar_erro(saida, cfg)["texto"], "linhas": linhas}


def escolher_pasta_mac():
    if sys.platform != "darwin":
        return None
    script = ['tell application "System Events"', "activate",
              'set p to POSIX path of (choose folder with prompt "Escolhe a pasta de destino")',
              "end tell", "return p"]
    cmd = ["osascript"]
    for l in script:
        cmd += ["-e", l]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip().rstrip("/") or None


# ------------------------------------------------------------------------- http --

def origem_permitida(origem, cfg=None):
    """Sem Origin = curl na própria máquina. Com Origin, só a extensão com o ID fixo."""
    if origem is None:
        return True
    m = re.match(r"^chrome-extension://([a-p]{32})$", origem)
    if not m:
        return False
    ok = {EXTENSAO_ID}
    ok.update((cfg or {}).get("extensoes_extras", []))
    return m.group(1) in ok


def host_permitido(host):
    """Barra DNS rebinding: o Host tem que ser o do próprio servidor."""
    return (host or "").lower() in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)


def info_status(cfg):
    res = cfg.get("resolucao_max") or 0
    subs = {"sample": "WAV", "referencia": "MP3",
            "video": "MP4 H.264 " + (("até %dp" % res) if res else "sem limite"), "video_max": "MP4 máxima"}
    return {
        "ok": True, "versao_servidor": VERSAO_SERVIDOR, "build": BUILD,
        "ytdlp": bool(FER.ytdlp), "ytdlp_versao": FER.versao, "ytdlp_origem": FER.origem, "ytdlp_canal": FER.canal,
        "ffmpeg": bool(FER.ffmpeg), "js": bool(FER.deno or FER.node),
        "cookies": cfg["cookies"], "resolucao_max": res,
        "destinos": [{"id": d["id"], "rotulo": d["rotulo"]} for d in cfg["destinos"]],
        "perfis": [{"id": k, "rotulo": v["rotulo"], "tipo": v["tipo"], "sub": subs[k],
                    "destino": cfg["perfil_destino"].get(k)} for k, v in PERFIS.items()],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        origem = self.headers.get("Origin", "")
        # Qualquer extensão lê o erro 403 (pra mostrar "extensão não reconhecida");
        # os dados só saem pra extensão permitida (ver _liberado).
        if re.match(r"^chrome-extension://", origem):
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _json(self, code, obj):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _liberado(self, cfg):
        if not host_permitido(self.headers.get("Host")):
            self._json(403, {"ok": False, "erro": "host não permitido", "codigo": "host"})
            return False
        origem = self.headers.get("Origin")
        if not origem_permitida(origem, cfg):
            log("origem recusada:", origem)
            self._json(403, {"ok": False, "codigo": "origem",
                             "erro": "O servidor não reconhece esta extensão. Remove ela em chrome://extensions "
                                     "e carrega a pasta extensao/ de novo."})
            return False
        return True

    def _corpo(self):
        tam = int(self.headers.get("Content-Length", 0) or 0)
        if tam > 65536:
            raise ValueError("corpo grande demais")
        dados = json.loads(self.rfile.read(tam) or b"{}")
        if not isinstance(dados, dict):
            raise ValueError("corpo precisa ser um objeto")
        return dados

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        cfg = carregar_config()
        if not self._liberado(cfg):
            return
        ro = urlparse(self.path)
        q = parse_qs(ro.query)
        if ro.path == "/status":
            return self._json(200, info_status(cfg))
        if ro.path == "/progresso":
            return self._json(200, FILA.snapshot())
        if ro.path == "/config":
            return self._json(200, {"ok": True, "config": cfg, "status": info_status(cfg)})
        if ro.path == "/historico":
            try:
                n = max(1, min(100, int((q.get("n") or ["20"])[0])))
            except ValueError:
                n = 20
            return self._json(200, {"ok": True, "itens": historico(cfg, n)})
        if ro.path == "/diagnostico":
            return self._json(200, diagnostico())
        self._json(404, {"ok": False, "erro": "rota desconhecida"})

    def do_POST(self):
        cfg = carregar_config()
        if not self._liberado(cfg):
            return
        try:
            corpo = self._corpo()
        except Exception:
            return self._json(400, {"ok": False, "erro": "corpo inválido"})
        rota = urlparse(self.path).path

        if rota == "/baixar":
            return self._baixar(cfg, corpo)
        if rota == "/cancelar":
            ok = FILA.cancelar(corpo.get("id"))
            return self._json(200 if ok else 404, {"ok": ok, "erro": None if ok else "nada pra cancelar"})
        if rota == "/mostrar":
            return self._mostrar(cfg, corpo)
        if rota == "/config":
            novo, erros = validar_config(dict(cfg, **corpo))
            if erros:
                return self._json(400, {"ok": False, "erro": "; ".join(erros)})
            for d in novo["destinos"]:
                try:
                    os.makedirs(d["caminho"], exist_ok=True)
                except OSError:
                    pass
            salvar_config(novo)
            return self._json(200, {"ok": True, "config": novo, "status": info_status(novo)})
        if rota == "/escolher_pasta":
            c = escolher_pasta_mac()
            if not c:
                return self._json(200, {"ok": False, "cancelado": True})
            seguro = caminho_seguro(c)
            if not seguro:
                return self._json(400, {"ok": False, "erro": "A pasta precisa ficar dentro do teu usuário (ou em /Volumes)."})
            return self._json(200, {"ok": True, "caminho": seguro})
        if rota == "/atualizar":
            def _fazer():
                with TRAVA_YTDLP:
                    atualizar_ytdlp("manual")
            threading.Thread(target=_fazer, daemon=True).start()
            return self._json(202, {"ok": True})
        self._json(404, {"ok": False, "erro": "rota desconhecida"})

    def _baixar(self, cfg, corpo):
        vid = extrair_id(corpo.get("url", ""))
        perfil = corpo.get("perfil") or COMPAT_FORMATO.get(corpo.get("formato"))
        if not vid or perfil not in PERFIS:
            return self._json(400, {"ok": False, "erro": "URL do YouTube ou perfil inválido."})
        ids = [d["id"] for d in cfg["destinos"]]
        destino = corpo.get("destino") if corpo.get("destino") in ids else cfg["perfil_destino"][perfil]
        if not FER.ytdlp:
            return self._json(500, {"ok": False, "erro": "yt-dlp não encontrado. Roda o instalar.sh do servidor."})
        if not FER.ffmpeg:
            return self._json(500, {"ok": False, "erro": "ffmpeg não encontrado. Roda o instalar.sh do servidor."})
        if not corpo.get("forcar"):
            ja = ja_baixado(cfg, vid, perfil, destino)
            if ja:
                return self._json(200, {"ok": True, "ja_existe": True, "arquivo": ja["arquivo"], "titulo": ja.get("titulo")})
        repetido = FILA.repetido(vid, perfil, destino)
        if repetido:
            return self._json(200, {"ok": True, "id": repetido, "na_fila": True})
        url = "https://www.youtube.com/watch?v=" + vid
        job = Job(url, perfil, destino, str(corpo.get("titulo") or "")[:200])
        pos = FILA.adicionar(job)
        self._json(202, {"ok": True, "id": job.id, "posicao": pos})

    def _mostrar(self, cfg, corpo):
        arq = None
        if corpo.get("id") is not None:
            j = FILA.achar(corpo.get("id"))
            arq = (j or {}).get("arquivo") or (j or {}).get("pasta")
        elif corpo.get("arquivo"):
            arq = corpo["arquivo"]
        else:
            for r in FILA.snapshot()["recentes"]:
                if r.get("arquivo"):
                    arq = r["arquivo"]
                    break
        if arq and caminho_permitido(arq, cfg) and os.path.exists(arq):
            subprocess.Popen(["open", "-R", arq] if os.path.isfile(arq) else ["open", arq])
            return self._json(200, {"ok": True})
        self._json(404, {"ok": False, "erro": "nada pra mostrar"})


def main():
    cfg = carregar_config()
    if not os.path.exists(ARQ_CONFIG):
        salvar_config(cfg)
    for d in cfg["destinos"]:
        try:
            os.makedirs(d["caminho"], exist_ok=True)
        except OSError as e:
            log("não consegui criar", d["caminho"], e)
    podar_log()
    log("Extrator Caramujo v%d (build %s) em http://%s:%d" % (VERSAO_SERVIDOR, BUILD, HOST, PORT))
    log("yt-dlp:", FER.ytdlp or "AUSENTE", FER.versao or "", "(%s)" % (FER.origem or "-"),
        "| ffmpeg:", FER.ffmpeg or "AUSENTE", "| js:", FER.deno or FER.node or "AUSENTE (vai dar 403)")
    retomar()
    threading.Thread(target=loop_worker, daemon=True).start()
    threading.Thread(target=loop_update, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
