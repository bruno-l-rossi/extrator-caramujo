# Extrator Caramujo

Extensão do Chrome, 100% local, sem servidor. Com um vídeo do YouTube aberto, clica no ícone e escolhe: **MP3** (192 kbps) ou **MP4**. Vem junto um mover do macOS que leva os arquivos direto pras suas pastas em Music/@rideblan33.

## Instalar a extensão (uma vez só)

1. Abre `chrome://extensions` no Chrome.
2. Liga o **Modo do desenvolvedor** (canto superior direito).
3. Clica em **Carregar sem compactação** e seleciona a pasta `extensao/` que está aqui dentro.
4. Fixa o ícone na barra (puxa pelo ícone de quebra-cabeça).

Se você já tinha instalado a versão anterior: remove ela em `chrome://extensions` e carrega de novo, porque a pasta do projeto mudou de nome.

## Instalar o mover (uma vez só)

O Chrome só deixa extensão gravar dentro de Downloads. O mover resolve isso: um agente nativo do macOS (launchd) vigia as subpastas `Downloads/Samples` e `Downloads/Inspiracoes` e, segundos depois que um arquivo cai ali, move ele pro destino final.

No Terminal:

```
bash "/Users/bruno-l-rossi/Documents/Claude Cowork/OUTPUTS/extrator-caramujo/mover/instalar.sh"
```

O instalador cria as pastas que faltarem e ativa o agente. Pra remover depois, roda o `desinstalar.sh` da mesma pasta.

### Como o mover funciona

- O launchd (mecanismo nativo do macOS, sem app rodando em background) observa as 2 subpastas de Downloads.
- Qualquer arquivo completo que aparecer ali é movido em 2 ou 3 segundos. Downloads em andamento (`.crdownload`) são ignorados até terminarem.
- Vale pra qualquer arquivo que cair nessas subpastas, não só os da extensão. Se você arrastar um WAV pra `Downloads/Samples` no Finder, ele vai pra Music também. Como essas subpastas só existem por causa da extensão, na prática é ela que alimenta.
- Se já existir arquivo com o mesmo nome no destino, o novo ganha um sufixo de hora em vez de sobrescrever.

### Mapa das pastas

| Opção no popup | Passagem (Downloads) | Destino final |
|---|---|---|
| Downloads | ~/Downloads | fica lá mesmo |
| Samples | ~/Downloads/Samples | ~/Music/@rideblan33/Samples |
| Inspiração | ~/Downloads/Inspiracoes | ~/Music/@rideblan33/Inspiration |

Pra mudar um destino no futuro: edita os 2 caminhos no fim do `mover/mover-caramujo.sh` e roda o `instalar.sh` de novo.

## Usar

1. Abre um vídeo no YouTube (Shorts também funciona).
2. Clica no ícone do Extrator Caramujo.
3. Escolhe o destino e clica em **Áudio** ou **Vídeo**.

A escolha de pasta fica salva pra próxima vez.

## Sobre a API do YouTube

A extensão fala com a API interna do YouTube por 3 rotas diferentes (clientes iOS, Android e TV), com fallback automático: se uma rota quebrar, ela tenta a próxima sozinha. Isso absorve boa parte das mudanças que o YouTube faz.

O que não dá pra automatizar: quando o YouTube muda a estrutura da API em si (acontece algumas vezes por ano), as 3 rotas caem juntas e o código precisa de ajuste manual. Ferramentas como o yt-dlp resolvem isso com um time de voluntários soltando atualização toda semana; uma extensão caseira não tem esse luxo. Então sim, nesse caso me aciona: aparece o erro "YouTube bloqueou a extração" no popup, você me chama, eu atualizo. Se um dia isso virar incômodo frequente, a saída é a versão com app local usando yt-dlp, que se atualiza sozinho com um comando.

## Outras limitações

**Qualidade do MP4.** O YouTube só entrega vídeo+áudio juntos num arquivo só até 360p (às vezes 720p). Acima disso ele separa as trilhas, e juntar exige ffmpeg, que não roda dentro de extensão. Pra 1080p+, mesmo caminho: versão com app local.

**Vídeos longos no MP3.** A conversão roda na memória do navegador. Beat e música de até uns 20 minutos vai tranquilo; podcast de 3 horas pode pesar.

**Uso pessoal.** Baixar do YouTube vai contra os termos da plataforma. Referência e estudo no estúdio é uma coisa; redistribuir ou soltar sample sem liberar direito é outra. Isso fica contigo.

## Estrutura

```
extensao/             # carregar esta pasta no Chrome
├── manifest.json     # permissões e config
├── popup.html/js     # a janelinha com os 2 botões
├── background.js     # busca os streams na API do YouTube
├── offscreen.html/js # converte o áudio pra MP3 (lamejs)
├── lib/lame.min.js   # encoder MP3
└── icons/

mover/                # leva os arquivos pra Music/@rideblan33
├── instalar.sh       # roda uma vez no Terminal
├── desinstalar.sh
├── mover-caramujo.sh # o script que move (destinos editáveis aqui)
└── com.caramujo.mover.plist
```
