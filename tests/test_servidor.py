# -*- coding: utf-8 -*-
"""Testes do servidor. Rodar:  python3 -m unittest discover -s tests -v
Sem dependência externa. Usa um yt-dlp falso pra testar a fila, a escada de
tentativas, o cancelamento e o vigia de travamento sem tocar no YouTube."""

import base64
import hashlib
import http.client
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="caramujo-test-")
os.environ["HOME"] = TMP
os.environ["CARAMUJO_HOME"] = os.path.join(TMP, ".caramujo")

spec = importlib.util.spec_from_file_location("srv", os.path.join(RAIZ, "servidor", "servidor_caramujo.py"))
srv = importlib.util.module_from_spec(spec)
sys.modules["srv"] = srv
spec.loader.exec_module(srv)

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
a = sys.argv[1:]
modo = os.environ.get("CARAMUJO_FAKE", "ok")
url = a[-1]
if modo == "403_sem_cache" and "--no-cache-dir" not in a:
    print("ERROR: unable to download video data: HTTP Error 403: Forbidden"); sys.exit(1)
if modo == "privado":
    print("ERROR: [youtube] abc: Private video. Sign in if you've been granted access"); sys.exit(1)
if modo == "mudo":
    print("[youtube] abc: Downloading webpage", flush=True); time.sleep(60); sys.exit(0)
saida = a[a.index("-o") + 1]
pasta = os.path.dirname(saida)
info = None
for i, x in enumerate(a):
    if x == "--print-to-file":
        info = a[i + 2]
ext = "wav" if "wav" in a else ("mp3" if "mp3" in a else "mp4")
lento = modo == "lento"
for n in range(1, 6):
    print("CRMJ|downloading|%d|1000|NA|2000.0|1|251|SINGLE|Titulo Fake" % (n * 200), flush=True)
    time.sleep(2 if lento else 0)
print("CRMJ|finished|1000|1000|NA|2000.0|NA|251|SINGLE|Titulo Fake", flush=True)
open(os.path.join(pasta, "Titulo Fake.f251.webm.part"), "w").write("x")
print("CRMJPP|started|ExtractAudio", flush=True)
alvo = os.path.join(pasta, "Titulo Fake." + ext)
open(alvo, "wb").write(b"dados")
print("CRMJPP|started|MoveFiles", flush=True)
vid = url.split("v=")[-1]
if info:
    open(info, "w").write(json.dumps({"id": vid, "title": "Titulo Fake", "channel": "Canal Fake",
                                     "duration": 10, "webpage_url": url, "filepath": alvo}) + "\n")
'''


def instalar_fake():
    d = os.path.join(TMP, "fake")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "yt-dlp")
    with open(p, "w") as f:
        f.write(FAKE)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        for f in (srv.ARQ_ESTADO, srv.ARQ_CONFIG):
            if os.path.exists(f):
                os.remove(f)
        srv.FER.ytdlp = "/x/yt-dlp"
        srv.FER.versao = "2026.11.16.123456"
        srv.FER.deno = "/x/deno"
        srv.FER.node = None
        srv.FER.ffmpeg = "/x/ffmpeg"
        srv.FILA = srv.Fila()


class TestErros(Base):
    def cls(self, *linhas, **cfg):
        return srv.classificar_erro(list(linhas), cfg)

    def test_sem_internet_nao_vira_restricao_de_idade(self):
        # regressão A-02: "age" casava com "webpage"
        c = self.cls("ERROR: [youtube] abc: Unable to download webpage: <urlopen error [Errno 8] "
                     "nodename nor servname provided, or not known>")
        self.assertEqual(c["nome"], "rede")
        self.assertTrue(c["final"])

    def test_webpage_sozinho_nao_e_idade(self):
        c = self.cls("ERROR: [youtube] abc: Unable to download webpage: something odd")
        self.assertNotEqual(c["nome"], "idade")

    def test_privado_indisponivel_disco_live(self):
        self.assertEqual(self.cls("ERROR: Private video. Sign in if you've been granted access")["nome"], "privado")
        self.assertEqual(self.cls("ERROR: Video unavailable. This video has been removed")["nome"], "indisponivel")
        self.assertEqual(self.cls("ERROR: [Errno 28] No space left on device")["nome"], "disco")
        self.assertEqual(self.cls("ERROR: This live event will begin in 2 hours.")["nome"], "live")

    def test_idade_final_so_sem_cookies(self):
        msg = "ERROR: Sign in to confirm your age. This video may be inappropriate for some users."
        self.assertTrue(self.cls(msg, cookies=False)["final"])
        self.assertFalse(self.cls(msg, cookies=True)["final"])
        self.assertEqual(self.cls(msg)["nome"], "idade")

    def test_bot_e_403(self):
        self.assertEqual(self.cls("ERROR: Sign in to confirm you’re not a bot")["nome"], "bot")
        a = self.cls("ERROR: unable to download video data: HTTP Error 403: Forbidden", cookies=False)
        b = self.cls("ERROR: unable to download video data: HTTP Error 403: Forbidden", cookies=True)
        self.assertEqual((a["nome"], a["acao"], a["final"]), ("403", "cookies", False))
        self.assertEqual(b["acao"], "tentar")

    def test_extracao_travou_desconhecido(self):
        self.assertEqual(self.cls("ERROR: Unable to extract nsig function")["nome"], "extracao")
        self.assertEqual(self.cls("ERROR: travou sem resposta")["nome"], "travou")
        c = self.cls("ERROR: algo nunca visto")
        self.assertEqual(c["nome"], "desconhecido")
        self.assertIn("algo nunca visto", c["texto"])

    def test_sem_mensagem(self):
        self.assertEqual(srv.classificar_erro([])["nome"], "desconhecido")


class TestProgresso(Base):
    def test_parse_download(self):
        p = srv.parse_progress("CRMJ|downloading|1024|58002|NA|2048.5|3|251|SINGLE|Minha | Música")
        self.assertEqual(p["tipo"], "dl")
        self.assertEqual(p["baixado"], 1024.0)
        self.assertEqual(p["total"], 58002.0)
        self.assertEqual(p["vel"], 2048.5)
        self.assertTrue(p["unico"])
        self.assertEqual(p["titulo"], "Minha | Música")

    def test_parse_usa_estimativa_e_na(self):
        p = srv.parse_progress("CRMJ|downloading|10|NA|500|NA|NA|137|140|T")
        self.assertEqual(p["total"], 500.0)
        self.assertIsNone(p["vel"])
        self.assertFalse(p["unico"])

    def test_parse_pp_e_lixo(self):
        self.assertEqual(srv.parse_progress("CRMJPP|started|ExtractAudio"),
                         {"tipo": "pp", "status": "started", "pp": "ExtractAudio"})
        self.assertIsNone(srv.parse_progress("[download] 10%"))
        self.assertIsNone(srv.parse_progress("CRMJ|curto"))

    def test_video_duas_etapas_nunca_volta(self):
        pr = srv.Progresso("video")
        vistos = []
        for fid, fim in (("137", 0.5), ("137", 1.0), ("140", 0.0), ("140", 0.5), ("140", 1.0)):
            p = {"formato": fid, "unico": False, "status": "finished" if fim == 1.0 else "downloading",
                 "baixado": fim * 100, "total": 100.0, "vel": 1.0, "eta": 1.0}
            vistos.append(pr.atualizar(p)["pct"])
        self.assertEqual(vistos, sorted(vistos))
        self.assertAlmostEqual(vistos[1], 45.0, places=1)
        self.assertAlmostEqual(vistos[-1], 90.0, places=1)

    def test_video_arquivo_unico_chega_a_90(self):
        pr = srv.Progresso("video")
        r = pr.atualizar({"formato": "22", "unico": True, "status": "finished",
                          "baixado": 10.0, "total": 10.0, "vel": None, "eta": None})
        self.assertAlmostEqual(r["pct"], 90.0, places=1)

    def test_audio_etapa(self):
        pr = srv.Progresso("audio")
        r = pr.atualizar({"formato": "251", "unico": True, "status": "downloading",
                          "baixado": 50.0, "total": 100.0, "vel": 1.0, "eta": 1.0})
        self.assertEqual(r["etapa"], "áudio")
        self.assertAlmostEqual(r["pct"], 45.0, places=1)


class TestComando(Base):
    def cmd(self, perfil, passo=None, **cfg):
        c = srv.carregar_config()
        c.update(cfg)
        return srv.montar_comando("https://www.youtube.com/watch?v=aaaaaaaaaaa", perfil, "/d", passo or [], "/tmp/i.json", c)

    def test_base(self):
        c = self.cmd("sample")
        self.assertIn("--ignore-config", c)
        self.assertEqual(c.count("--progress-template"), 2)
        self.assertEqual(c[-1], "https://www.youtube.com/watch?v=aaaaaaaaaaa")
        self.assertIn("--embed-metadata", c)
        self.assertIn("deno:/x/deno", c)

    def test_perfis(self):
        self.assertIn("wav", self.cmd("sample"))
        self.assertNotIn("mp3", self.cmd("sample"))
        r = self.cmd("referencia")
        self.assertIn("mp3", r)
        self.assertEqual(r[r.index("--audio-quality") + 1], "2")
        v = self.cmd("video")
        self.assertEqual(v[v.index("-S") + 1], "vcodec:h264,res:1080,acodec:m4a")
        v0 = self.cmd("video", resolucao_max=0)
        self.assertEqual(v0[v0.index("-S") + 1], "vcodec:h264,acodec:m4a")
        self.assertIn("bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b", self.cmd("video_max"))

    def test_passo_vai_antes_da_url(self):
        c = self.cmd("sample", ["--no-cache-dir", "--force-ipv4"])
        self.assertEqual(c[-3:-1], ["--no-cache-dir", "--force-ipv4"])

    def test_ytdlp_velho_sem_flags_novas(self):
        srv.FER.versao = "2024.01.01"
        self.assertNotIn("--js-runtimes", self.cmd("sample"))
        self.assertNotIn("--remote-components", self.cmd("sample"))

    def test_node_de_reserva(self):
        srv.FER.deno = None
        srv.FER.node = "/x/node"
        self.assertIn("node:/x/node", self.cmd("sample"))


class TestEscada(Base):
    def nomes(self, cfg, estado):
        return [p["nome"] for p in srv.montar_escada(cfg, estado)]

    def test_ordem_padrao(self):
        n = self.nomes(srv.carregar_config(), {})
        self.assertEqual(n[:3], ["padrão", "sem cache", "yt-dlp novo"])
        self.assertIn("cliente android_vr", n)
        self.assertEqual(n[-1], "IPv4")

    def test_cookies_so_quando_ligado(self):
        cfg = srv.carregar_config()
        self.assertNotIn("login do navegador", self.nomes(cfg, {}))
        cfg["cookies"] = True
        self.assertEqual(self.nomes(cfg, {})[-1], "login do navegador")

    def test_vencedora_vai_pra_frente_e_expira(self):
        cfg = srv.carregar_config()
        n = self.nomes(cfg, {"vencedora": {"nome": "cliente tv", "quando": time.time()}})
        self.assertEqual(n[0], "cliente tv")
        n = self.nomes(cfg, {"vencedora": {"nome": "cliente tv", "quando": time.time() - 90000}})
        self.assertEqual(n[0], "padrão")
        n = self.nomes(cfg, {"vencedora": {"nome": "yt-dlp novo", "quando": time.time()}})
        self.assertEqual(n[0], "padrão")


class TestUrlEOrigem(Base):
    def test_extrair_id(self):
        ok = "dQw4w9WgXcQ"
        for u in ("https://www.youtube.com/watch?v=%s&list=PL1&t=9" % ok, "https://youtu.be/%s?t=3" % ok,
                  "https://www.youtube.com/shorts/%s" % ok, "https://www.youtube.com/live/%s" % ok,
                  "https://music.youtube.com/watch?v=%s" % ok, "https://m.youtube.com/watch?v=%s" % ok):
            self.assertEqual(srv.extrair_id(u), ok, u)
        for u in ("https://evil.com/watch?v=%s" % ok, "https://youtube.com.evil.com/watch?v=%s" % ok,
                  "https://www.youtube.com/@canal", "https://www.youtube.com/playlist?list=PL1", "lixo", ""):
            self.assertIsNone(srv.extrair_id(u), u)

    def test_origem_e_host(self):
        self.assertTrue(srv.origem_permitida(None))
        self.assertTrue(srv.origem_permitida("chrome-extension://" + srv.EXTENSAO_ID))
        self.assertFalse(srv.origem_permitida("chrome-extension://" + "a" * 32))
        self.assertFalse(srv.origem_permitida("https://evil.com"))
        self.assertTrue(srv.origem_permitida("chrome-extension://" + "a" * 32, {"extensoes_extras": ["a" * 32]}))
        self.assertTrue(srv.host_permitido("127.0.0.1:%d" % srv.PORT))
        self.assertTrue(srv.host_permitido("localhost:%d" % srv.PORT))
        self.assertFalse(srv.host_permitido("evil.com:%d" % srv.PORT))
        self.assertFalse(srv.host_permitido(None))


class TestConfig(Base):
    def test_padrao_valido(self):
        cfg, erros = srv.validar_config({})
        self.assertEqual(erros, [])
        self.assertEqual([d["id"] for d in cfg["destinos"]], ["downloads", "samples", "inspiration"])
        self.assertTrue(cfg["destinos"][1]["caminho"].startswith(TMP))

    def test_pasta_fora_do_usuario(self):
        _, erros = srv.validar_config({"destinos": [{"id": "x", "rotulo": "X", "caminho": "/etc"}]})
        self.assertTrue(erros)
        _, erros = srv.validar_config({"destinos": [{"id": "x", "rotulo": "X", "caminho": "/Volumes/SSD/beats"}]})
        self.assertEqual(erros, [])

    def test_ids_ruins_e_repetidos(self):
        d = {"id": "a", "rotulo": "A", "caminho": "~/a"}
        self.assertTrue(srv.validar_config({"destinos": [d, dict(d)]})[1])
        self.assertTrue(srv.validar_config({"destinos": [{"id": "A B", "rotulo": "x", "caminho": "~/a"}]})[1])

    def test_perfil_cai_no_primeiro_destino_se_o_dele_sumiu(self):
        cfg, erros = srv.validar_config({"destinos": [{"id": "so", "rotulo": "So", "caminho": "~/so"}]})
        self.assertEqual(erros, [])
        self.assertEqual(set(cfg["perfil_destino"].values()), {"so"})

    def test_valores_invalidos(self):
        self.assertTrue(srv.validar_config({"resolucao_max": 999})[1])
        self.assertTrue(srv.validar_config({"cookies": "sim"})[1])
        self.assertTrue(srv.validar_config({"navegador_cookies": "netscape"})[1])
        self.assertTrue(srv.validar_config({"perfil_destino": {"sample": "nao_existe"}})[1])
        self.assertTrue(srv.validar_config({"clientes_alternativos": ["ok", "Mau Cliente!"]})[1])
        self.assertTrue(srv.validar_config({"extensoes_extras": ["curto"]})[1])
        self.assertTrue(srv.validar_config("lixo")[1])

    def test_salvar_e_carregar(self):
        cfg = srv.carregar_config()
        cfg["cookies"] = True
        cfg["resolucao_max"] = 720
        srv.salvar_config(cfg)
        again = srv.carregar_config()
        self.assertTrue(again["cookies"])
        self.assertEqual(again["resolucao_max"], 720)

    def test_arquivo_corrompido_volta_pro_padrao(self):
        with open(srv.ARQ_CONFIG, "w") as f:
            f.write("{nao e json")
        self.assertEqual(srv.carregar_config()["resolucao_max"], 1080)

    def test_caminho_permitido(self):
        cfg = srv.carregar_config()
        pasta = cfg["destinos"][1]["caminho"]
        os.makedirs(pasta, exist_ok=True)
        self.assertTrue(srv.caminho_permitido(os.path.join(pasta, "a.wav"), cfg))
        self.assertFalse(srv.caminho_permitido("/etc/passwd", cfg))
        self.assertFalse(srv.caminho_permitido(os.path.join(pasta, "..", "..", "x"), cfg))


class TestArquivos(Base):
    def test_origens_e_duplicado(self):
        cfg = srv.carregar_config()
        d = os.path.join(TMP, "dup")
        os.makedirs(d, exist_ok=True)
        arq = os.path.join(d, "a.wav")
        open(arq, "w").write("x")
        srv.registrar_origem(cfg, {"id_video": "aaaaaaaaaaa", "perfil": "sample", "destino": "samples",
                                   "arquivo": arq, "titulo": "A"})
        srv.registrar_origem(cfg, {"id_video": "bbbbbbbbbbb", "perfil": "sample", "destino": "samples",
                                   "arquivo": "/nao/existe.wav", "titulo": "B"})
        self.assertIsNotNone(srv.ja_baixado(cfg, "aaaaaaaaaaa", "sample", "samples"))
        self.assertIsNone(srv.ja_baixado(cfg, "aaaaaaaaaaa", "video", "samples"))     # outro perfil
        self.assertIsNone(srv.ja_baixado(cfg, "aaaaaaaaaaa", "sample", "downloads"))  # outro destino
        self.assertIsNone(srv.ja_baixado(cfg, "bbbbbbbbbbb", "sample", "samples"))    # arquivo sumiu
        h = srv.historico(cfg, 5)
        self.assertEqual([x["titulo"] for x in h], ["B", "A"])
        self.assertEqual([x["existe"] for x in h], [False, True])

    def test_limpar_parciais(self):
        d = os.path.join(TMP, "parciais")
        os.makedirs(d, exist_ok=True)
        for nome in ("a.f251.webm", "a.f137.mp4.part", "b.part", "c.ytdl", "d.temp.wav", "fim.wav",
                     "Song.fantastic.mp3", "Outra Musica.mp3"):
            open(os.path.join(d, nome), "w").write("x")
        velho = os.path.join(d, "velho.part")
        open(velho, "w").write("x")
        os.utime(velho, (time.time() - 3600, time.time() - 3600))
        n = srv.limpar_parciais(d, time.time() - 60)
        restam = sorted(os.listdir(d))
        self.assertEqual(n, 5)
        self.assertEqual(restam, ["Outra Musica.mp3", "Song.fantastic.mp3", "fim.wav", "velho.part"])


class TestFila(Base):
    def job(self, vid="aaaaaaaaaaa", perfil="sample"):
        return srv.Job("https://www.youtube.com/watch?v=" + vid, perfil, "samples", "T")

    def test_ordem_posicao_e_cancelar(self):
        f = srv.FILA
        a, b = self.job("aaaaaaaaaaa"), self.job("bbbbbbbbbbb")
        self.assertEqual(f.adicionar(a), 0)
        self.assertEqual(f.adicionar(b), 1)
        self.assertEqual(f.repetido("aaaaaaaaaaa", "sample", "samples"), a.id)
        self.assertIsNone(f.repetido("aaaaaaaaaaa", "video", "samples"))
        self.assertTrue(f.cancelar(b.id))
        self.assertFalse(f.cancelar(b.id))
        s = f.snapshot()
        self.assertEqual([j["id"] for j in s["fila"]], [a.id])
        self.assertEqual(s["recentes"][0]["estado"], "cancelado")
        self.assertIs(f.proximo(), a)
        self.assertEqual(f.snapshot()["ativo"]["id"], a.id)
        f.concluir(a)
        self.assertIsNone(f.snapshot()["ativo"])

    def test_estado_persistido_e_retomada(self):
        a = self.job("aaaaaaaaaaa")
        srv.FILA.adicionar(a)
        srv.FILA.proximo()           # a vira ativo
        b = self.job("bbbbbbbbbbb")
        srv.FILA.adicionar(b)
        # "reinicia" o servidor
        srv.FILA = srv.Fila()
        srv.retomar()
        s = srv.FILA.snapshot()
        self.assertEqual([j["id"] for j in s["fila"]], [b.id])
        self.assertEqual(s["recentes"][0]["estado"], "erro")
        self.assertIn("reiniciou", s["recentes"][0]["texto"])
        self.assertEqual(s["recentes"][0]["acao"], "tentar")


class TestExecucao(Base):
    """Roda o job de verdade contra um yt-dlp falso."""

    def setUp(self):
        super().setUp()
        srv.FER.ytdlp = instalar_fake()
        srv.FER.ffmpeg = None
        self.guardados = (srv.atualizar_ytdlp, srv.LIMITE_SILENCIO, srv.VIGIA_INTERVALO)
        srv.atualizar_ytdlp = lambda motivo: False
        for f in os.listdir(srv.carregar_config()["destinos"][1]["caminho"]) if os.path.isdir(srv.carregar_config()["destinos"][1]["caminho"]) else []:
            os.remove(os.path.join(srv.carregar_config()["destinos"][1]["caminho"], f))
        orig = srv.carregar_config()["arquivo_origens"]
        if os.path.exists(orig):
            os.remove(orig)

    def tearDown(self):
        srv.atualizar_ytdlp, srv.LIMITE_SILENCIO, srv.VIGIA_INTERVALO = self.guardados
        os.environ.pop("CARAMUJO_FAKE", None)

    def rodar(self, modo, perfil="sample", vid="aaaaaaaaaaa"):
        os.environ["CARAMUJO_FAKE"] = modo
        job = srv.Job("https://www.youtube.com/watch?v=" + vid, perfil, "samples", "titulo da aba")
        srv.FILA.adicionar(job)
        j = srv.FILA.proximo()
        srv.executar_job(j)
        srv.FILA.concluir(j)
        return j

    def test_sucesso_de_primeira(self):
        j = self.rodar("ok")
        self.assertEqual(j.estado, "ok", j.texto)
        self.assertEqual(j.pct, 100)
        self.assertTrue(j.arquivo.endswith("Titulo Fake.wav"))
        self.assertTrue(os.path.isfile(j.arquivo))
        self.assertEqual(j.titulo, "Titulo Fake")
        self.assertEqual(j.estrategia, "padrão")
        self.assertIsNone(srv.carregar_estado().get("vencedora"))
        h = srv.historico(srv.carregar_config(), 5)
        self.assertEqual(h[0]["canal"], "Canal Fake")
        self.assertEqual(h[0]["perfil"], "sample")
        # segundo clique no mesmo vídeo é duplicado
        self.assertIsNotNone(srv.ja_baixado(srv.carregar_config(), "aaaaaaaaaaa", "sample", "samples"))

    def test_perfil_define_extensao(self):
        self.assertTrue(self.rodar("ok", "referencia", "bbbbbbbbbbb").arquivo.endswith(".mp3"))
        self.assertTrue(self.rodar("ok", "video", "ccccccccccc").arquivo.endswith(".mp4"))

    def test_403_resolve_na_segunda_tentativa(self):
        j = self.rodar("403_sem_cache")
        self.assertEqual(j.estado, "ok", j.texto)
        self.assertEqual(j.estrategia, "sem cache")
        self.assertEqual(j.tentativa, 2)
        self.assertEqual(srv.carregar_estado()["vencedora"]["nome"], "sem cache")
        # na próxima, a vencedora vem primeiro
        self.assertEqual(srv.montar_escada(srv.carregar_config(), srv.carregar_estado())[0]["nome"], "sem cache")

    def test_erro_final_nao_tenta_o_resto(self):
        j = self.rodar("privado")
        self.assertEqual(j.estado, "erro")
        self.assertEqual(j.tentativa, 1)
        self.assertIn("privado", j.texto.lower())
        self.assertIsNone(j.acao)

    def test_cancelar_no_meio(self):
        os.environ["CARAMUJO_FAKE"] = "lento"
        job = srv.Job("https://www.youtube.com/watch?v=ddddddddddd", "sample", "samples", "x")
        srv.FILA.adicionar(job)
        j = srv.FILA.proximo()
        t = threading.Thread(target=srv.executar_job, args=(j,))
        t.start()
        for _ in range(100):
            if j.proc is not None and j.estado == "baixando":
                break
            time.sleep(0.1)
        self.assertTrue(srv.FILA.cancelar(j.id))
        t.join(20)
        self.assertFalse(t.is_alive())
        srv.FILA.concluir(j)
        self.assertEqual(j.estado, "cancelado")
        pasta = srv.carregar_config()["destinos"][1]["caminho"]
        self.assertFalse([n for n in os.listdir(pasta) if n.endswith(".part")])

    def test_vigia_mata_processo_mudo(self):
        srv.LIMITE_SILENCIO = 1
        srv.VIGIA_INTERVALO = 0.2
        t0 = time.time()
        j = self.rodar("mudo")
        self.assertLess(time.time() - t0, 25)
        self.assertEqual(j.estado, "erro")
        self.assertIn("travou", j.texto.lower())


class TestHttp(Base):
    @classmethod
    def setUpClass(cls):
        cls.httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.porta = cls.httpd.server_address[1]
        srv.PORT = cls.porta
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, metodo, rota, corpo=None, origem=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        h = {"Host": host or "127.0.0.1:%d" % self.porta}
        if origem:
            h["Origin"] = origem
        data = None
        if corpo is not None:
            data = json.dumps(corpo)
            h["Content-Type"] = "application/json"
        c.request(metodo, rota, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None), dict(r.getheaders())

    EXT = "chrome-extension://" + srv.EXTENSAO_ID

    def test_status_e_progresso(self):
        s, d, _ = self.req("GET", "/status", origem=self.EXT)
        self.assertEqual(s, 200)
        self.assertEqual(d["versao_servidor"], 4)
        self.assertEqual([p["id"] for p in d["perfis"]], ["sample", "referencia", "video", "video_max"])
        s, d, _ = self.req("GET", "/progresso", origem=self.EXT)
        self.assertEqual((s, d["ativo"], d["fila"]), (200, None, []))

    def test_bloqueios(self):
        s, d, h = self.req("GET", "/status", origem="https://evil.com")
        self.assertEqual(s, 403)
        self.assertNotIn("Access-Control-Allow-Origin", h)
        s, d, h = self.req("GET", "/status", origem="chrome-extension://" + "a" * 32)
        self.assertEqual((s, d["codigo"]), (403, "origem"))
        self.assertIn("Access-Control-Allow-Origin", h)   # pra extensão errada ler a explicação
        s, d, _ = self.req("GET", "/status", host="evil.com:%d" % self.porta)
        self.assertEqual((s, d["codigo"]), (403, "host"))
        s, _, _ = self.req("GET", "/status")               # curl local, sem Origin
        self.assertEqual(s, 200)

    def test_baixar_validacoes_e_cancelar(self):
        s, d, _ = self.req("POST", "/baixar", {"url": "https://evil.com/watch?v=aaaaaaaaaaa", "perfil": "sample"}, self.EXT)
        self.assertEqual(s, 400)
        s, d, _ = self.req("POST", "/baixar", {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "perfil": "nada"}, self.EXT)
        self.assertEqual(s, 400)
        u = {"url": "https://www.youtube.com/watch?v=eeeeeeeeeee&list=PL", "perfil": "sample", "titulo": "T"}
        s, d, _ = self.req("POST", "/baixar", u, self.EXT)
        self.assertEqual((s, d["posicao"]), (202, 0))
        s, d2, _ = self.req("POST", "/baixar", u, self.EXT)       # mesmo vídeo, mesmo perfil: não duplica
        self.assertEqual((s, d2.get("na_fila")), (200, True))
        s, p, _ = self.req("GET", "/progresso", origem=self.EXT)
        self.assertEqual(len(p["fila"]), 1)
        self.assertEqual(p["fila"][0]["url"], "https://www.youtube.com/watch?v=eeeeeeeeeee")
        s, _, _ = self.req("POST", "/cancelar", {"id": d["id"]}, self.EXT)
        self.assertEqual(s, 200)
        s, _, _ = self.req("POST", "/cancelar", {"id": d["id"]}, self.EXT)
        self.assertEqual(s, 404)

    def test_compat_formato_antigo(self):
        s, d, _ = self.req("POST", "/baixar", {"url": "https://youtu.be/fffffffffff", "formato": "mp3"}, self.EXT)
        self.assertEqual(s, 202)
        self.assertEqual(srv.FILA.snapshot()["fila"][0]["perfil"], "referencia")

    def test_config_post_mescla_e_valida(self):
        s, d, _ = self.req("POST", "/config", {"cookies": True}, self.EXT)
        self.assertEqual(s, 200)
        self.assertTrue(d["config"]["cookies"])
        self.assertEqual(len(d["config"]["destinos"]), 3)       # não perdeu o resto
        s, d, _ = self.req("POST", "/config", {"destinos": [{"id": "x", "rotulo": "X", "caminho": "/etc"}]}, self.EXT)
        self.assertEqual(s, 400)
        s, d, _ = self.req("POST", "/config", {"resolucao_max": 4321}, self.EXT)
        self.assertEqual(s, 400)

    def test_mostrar_recusa_fora_dos_destinos(self):
        s, _, _ = self.req("POST", "/mostrar", {"arquivo": "/etc/passwd"}, self.EXT)
        self.assertEqual(s, 404)

    def test_historico(self):
        s, d, _ = self.req("GET", "/historico?n=3", origem=self.EXT)
        self.assertEqual(s, 200)
        self.assertIsInstance(d["itens"], list)


class TestExtensao(unittest.TestCase):
    def setUp(self):
        self.ext = os.path.join(RAIZ, "extensao")
        if not os.path.exists(os.path.join(self.ext, "manifest.json")):
            self.skipTest("extensão ainda não existe")

    def test_build_igual(self):
        js = open(os.path.join(self.ext, "comum.js"), encoding="utf-8").read()
        m = re.search(r"BUILD_ESPERADO\s*=\s*'([^']+)'", js)
        self.assertEqual(m.group(1), srv.BUILD)

    def test_id_da_extensao_bate_com_a_key(self):
        man = json.load(open(os.path.join(self.ext, "manifest.json"), encoding="utf-8"))
        der = base64.b64decode(man["key"])
        h = hashlib.sha256(der).hexdigest()[:32]
        ident = "".join(chr(ord("a") + int(c, 16)) for c in h)
        self.assertEqual(ident, srv.EXTENSAO_ID)

    def test_permissoes_enxutas(self):
        man = json.load(open(os.path.join(self.ext, "manifest.json"), encoding="utf-8"))
        self.assertNotIn("tabs", man["permissions"])
        self.assertEqual(man["host_permissions"], ["http://127.0.0.1:8765/*"])

    def test_manifest_aponta_pra_arquivos_que_existem(self):
        man = json.load(open(os.path.join(self.ext, "manifest.json"), encoding="utf-8"))
        arqs = [man["background"]["service_worker"], man["action"]["default_popup"], man["options_page"]]
        arqs += list(man["icons"].values())
        for a in arqs:
            self.assertTrue(os.path.exists(os.path.join(self.ext, a)), a)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
