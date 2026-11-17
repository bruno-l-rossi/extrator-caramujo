# Extrator Caramujo

Baixa áudio (WAV ou MP3) ou vídeo (MP4) de qualquer vídeo do YouTube aberto na aba. Duas peças: a extensão do Chrome (os botões) e um servidor no teu Mac (yt-dlp, ffmpeg e deno fazem o trabalho pesado). Tudo roda na tua máquina.

## O que mudou na v4

- **Três botões por intenção.** Sample (WAV), Referência (MP3) e Vídeo (MP4 H.264, abre no Final Cut). Cada um já sabe a pasta.
- **Fila.** Clica em quantos vídeos quiser. Baixa um por vez, dá pra cancelar o atual ou tirar da fila.
- **Atalhos e clique direito.** Baixa sem abrir o popup, até de um link na busca do YouTube.
- **Menos 403.** O servidor usa o yt-dlp nightly, se atualiza sozinho e, se o YouTube recusar, tenta outros caminhos antes de desistir.
- **Sabe de onde veio cada arquivo.** Guarda URL, canal e data de tudo que baixa.
- **Aguenta reinício.** Se o servidor cair no meio, o popup avisa e limpa os restos.
- **Pastas pelas Opções**, sem editar código.

## Instalar (do zero ou vindo da v3)

### 1. O servidor

No Terminal:

```
bash "/Users/bruno-l-rossi/Documents/Claude Cowork/OUTPUTS/extrator-caramujo/servidor/instalar.sh"
```

Ele instala ffmpeg e deno pelo Homebrew (se faltarem), baixa o yt-dlp nightly pra `~/.caramujo/bin` e sobe o servidor. No fim tem que aparecer `ffmpeg True | js True`. Rodar de novo é seguro, e é o jeito de aplicar qualquer mudança no `servidor_caramujo.py`.

Precisa do Homebrew. Se não tiver, instala em https://brew.sh.

### 2. A extensão

A v4 tem ID fixo, e o servidor só aceita esse ID. Por isso:

1. Abre `chrome://extensions`.
2. Remove o Extrator Caramujo antigo, se tiver.
3. Liga o **Modo do desenvolvedor**, clica em **Carregar sem compactação** e escolhe a pasta `extensao/`.
4. Fixa o ícone na barra e aceita as notificações.

Se o popup disser que o servidor não reconhece a extensão, é porque ficou a versão antiga carregada. Repete o passo 2.

## Usar

Abre um vídeo e clica no ícone.

| Botão | Formato | Pasta padrão |
|---|---|---|
| Sample | WAV, direto do áudio do YouTube | Samples |
| Referência | MP3 (V2, uns 190 kbps) | Inspiration |
| Vídeo | MP4 H.264 até 1080p | Downloads |
| Vídeo na máxima qualidade (em "Mais opções") | MP4 com o que o YouTube tiver, até AV1 e 4K | Downloads |

O WAV mantém a taxa de amostragem da fonte (quase sempre 48 kHz). O FL Studio converte na importação.

**Atalhos** (mudam em `chrome://extensions/shortcuts`): Option+Shift+S sample, Option+Shift+R referência, Option+Shift+V vídeo. Valem pra aba aberta.

**Clique direito** na página de um vídeo ou num link do YouTube: "Caramujo: sample", "referência" ou "vídeo".

**Já baixou esse?** O popup avisa e oferece mostrar no Finder ou baixar de novo.

**Fora do YouTube** o popup mostra um campo pra colar o link, mais a lista dos últimos downloads.

**Pastas, resolução e login do Chrome** ficam em Opções (link no popup).

## De onde veio cada arquivo

Todo download vira uma linha em `~/Music/@rideblan33/origens.jsonl`: data, URL, título, canal, duração, perfil, pasta e caminho do arquivo. O Finder também mostra a URL em "De onde veio" (Get Info). Serve pra achar a fonte de um sample quando precisar liberar o direito.

## Se der erro

1. Clica em **Testar** no rodapé do popup. Ele roda um download de teste e mostra versão do yt-dlp, runtime JS e o que o YouTube respondeu. Copia o relatório e cola numa conversa comigo.
2. O servidor já tenta sozinho, nesta ordem: padrão, sem cache, yt-dlp atualizado, outros clientes do player, IPv4 e (se ligado) login do Chrome. O que funcionar vira o primeiro da próxima vez.
3. 403 que não passa: liga o login do Chrome nas Opções, ou no botão que aparece junto do erro. Na primeira vez o macOS pergunta se o python pode acessar "Chrome Safe Storage": Permitir sempre. Isso também libera vídeo com restrição de idade.
4. O log fica em `~/.caramujo/servidor.log`:

```
tail -50 ~/.caramujo/servidor.log
```

5. O popup mostra "servidor desatualizado"? Roda o `instalar.sh` de novo.

## Como funciona

- O servidor escuta só em `127.0.0.1:8765`. Aceita pedido da extensão com o ID fixo (vem da `key` do `manifest.json`) e confere o cabeçalho `Host`, o que barra site tentando chegar nele.
- Só baixa URL de vídeo do YouTube, e só pra pastas dentro do teu usuário (ou `/Volumes`).
- O yt-dlp nightly atualiza no login e a cada 24 h. Se a atualização falhar (rede ainda subindo, por exemplo), tenta de novo em 30 min.
- Download travado sem escrever nada por 3 min é encerrado. Processo órfão do ffmpeg morre junto.
- Estado, fila e últimos downloads ficam em `~/.caramujo/estado.json`. Configuração em `~/.caramujo/config.json`.

## Testes

```
python3 -m unittest discover -s tests
```

Rodam sem internet. Usam um yt-dlp falso pra testar fila, tentativas, cancelamento e travamento. O que depende do Mac (launchd, Finder, seletor de pasta, login do Chrome) a gente confere na mão.

## Estrutura

```
extensao/               # carregar no Chrome
├── manifest.json       # ID fixo (key), atalhos
├── popup.html/js       # os 3 botões, fila, recentes
├── background.js       # % no ícone, notificações, atalhos, clique direito
├── opcoes.html/js      # pastas, resolução, login do Chrome
├── comum.js            # funções compartilhadas e BUILD_ESPERADO
└── icons/

servidor/
├── servidor_caramujo.py   # fila, yt-dlp, perfis, origens, config
├── instalar.sh / desinstalar.sh
└── com.caramujo.servidor.plist

tests/test_servidor.py
CHANGELOG.md
PLANO-v4.md             # plano de trabalho e registro de progresso (pra IA retomar)
```

## Uso pessoal

Baixar do YouTube vai contra os termos da plataforma. Referência e estudo no estúdio é uma coisa. Soltar sample sem liberar o direito é outra. Isso fica contigo, e o `origens.jsonl` existe pra te ajudar nisso.
