# Extrator Caramujo

Baixa o áudio (MP3) ou o vídeo (MP4) de qualquer vídeo do YouTube aberto na aba. Duas peças: a extensão do Chrome (o botão) e um servidor local no teu Mac (yt-dlp + ffmpeg, que faz o trabalho pesado). Tudo roda na tua máquina.

## Por que tem servidor agora

A versão anterior tentava baixar direto pela extensão. Bateu no teto: o YouTube cifra o áudio de quase todo vídeo e pede login pra confirmar que você não é robô. Quebrar isso exige rodar o player do YouTube, que muda toda semana. O yt-dlp resolve isso com um time atualizando sem parar, e o ffmpeg converte MP3/MP4 de verdade. Então a extensão virou só o botão; quem baixa é o servidor.

Ganho: MP3 real, MP4 em qualquer qualidade (1080p, 4K), e não quebra quando o YouTube muda. Quando precisar de manutenção, é só `yt-dlp -U` no terminal, sem mexer no código.

## Instalar (2 passos, uma vez só)

### 1. O servidor

No Terminal:

```
bash "/Users/bruno-l-rossi/Documents/Claude Cowork/OUTPUTS/extrator-caramujo/servidor/instalar.sh"
```

Ele instala o yt-dlp e o ffmpeg, cria as pastas em Music/@rideblan33 e sobe o servidor. No fim mostra `{"ok": true, "ytdlp": true, "ffmpeg": true}`: é isso que você quer ver.

Precisa do Homebrew pro ffmpeg. Se não tiver, instala em https://brew.sh e roda o instalar de novo.

### 2. A extensão

1. Abre `chrome://extensions`.
2. Liga o **Modo do desenvolvedor** (canto superior direito).
3. **Carregar sem compactação** e seleciona a pasta `extensao/`.
4. Fixa o ícone na barra.

Se já tinha uma versão antiga instalada, remove ela antes (o manifest mudou bastante).

## Usar

1. Abre um vídeo no YouTube (Shorts e Live também).
2. Clica no ícone do Extrator Caramujo.
3. Escolhe a pasta e clica em **Áudio** ou **Vídeo**.

Se o servidor estiver fora do ar, o popup avisa na hora que você abre. A pasta escolhida fica salva.

O popup mostra uma barra de progresso enquanto o yt-dlp trabalha. É normal levar de alguns segundos a um minuto, dependendo do tamanho do vídeo: o servidor só responde quando termina de baixar e converter. A barra é uma estimativa por tempo (não dá pra ler o progresso real do yt-dlp pela arquitetura atual), mas serve pra mostrar que está rolando, não travado.

Pode fechar e reabrir o popup no meio do download: o estado fica guardado no background, então ele volta mostrando a barra na posição certa em vez de recomeçar do zero.

## As pastas

| Opção no popup | Onde salva |
|---|---|
| Downloads | ~/Downloads |
| Samples | ~/Music/@rideblan33/Samples |
| Inspiration | ~/Music/@rideblan33/Inspiration |

Agora salva direto no destino final, sem passar por Downloads (o servidor escreve onde quiser na tua máquina, coisa que a extensão sozinha não podia). Pra mudar ou adicionar um caminho: edita o dicionário `DESTINOS` no topo do `servidor/servidor_caramujo.py` e reinicia o servidor (`launchctl unload` e `load` do plist, ou só reinicia o Mac).

## O servidor no dia a dia

- Sobe sozinho no login (launchd, igual ao mover de antes). Não precisa abrir nada.
- Escuta só em `127.0.0.1:8765`, ou seja, só a tua máquina alcança. Nada exposto pra rede.
- Só aceita pedido vindo da extensão do Chrome.
- Log em `~/.caramujo/servidor.log` se algo der errado.
- Pra remover tudo: `bash servidor/desinstalar.sh`.

## Manutenção

Quando um download falhar com erro de "Unable to extract" ou parecido, é o yt-dlp desatualizado. Conserto numa linha:

```
python3 -m pip install --user --upgrade yt-dlp --break-system-packages
```

Esse é o ponto inteiro de ter migrado: a manutenção virou um comando que você mesmo roda, em vez de me acionar pra reescrever a extensão.

## Uso pessoal

Baixar do YouTube vai contra os termos da plataforma. Referência e estudo no estúdio é uma coisa; redistribuir ou soltar sample sem liberar direito é outra. Isso fica contigo.

## Estrutura

```
extensao/             # carregar no Chrome
├── manifest.json
├── popup.html/js     # o botão, manda a URL pro servidor
├── background.js     # repassa pro localhost:8765
└── icons/

servidor/             # o que baixa de verdade
├── instalar.sh       # roda uma vez no Terminal
├── desinstalar.sh
├── servidor_caramujo.py   # yt-dlp + ffmpeg (destinos editáveis no topo)
└── com.caramujo.servidor.plist
```
