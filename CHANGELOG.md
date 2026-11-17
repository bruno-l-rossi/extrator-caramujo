# Changelog

Cada versão nasceu de uma dor. O que quebrou, o que a gente fez.

## 4.0.0 (2026-11-16)

**Dor:** baixar em lote era lento e cheio de passo manual. O arquivo nem sempre chegava no formato certo pro FL Studio e pro Final Cut. Erro mandava abrir o Terminal. Ninguém guardava de onde o sample veio.

- Três botões por intenção: Sample (WAV), Referência (MP3), Vídeo (MP4 H.264 até 1080p). Vídeo na máxima qualidade em "Mais opções".
- Fila de downloads, cancelar o atual, tirar item da fila.
- Atalhos de teclado (Option+Shift+S, R, V) e menu de clique direito, inclusive em link.
- `origens.jsonl` com a fonte de cada download, e "De onde veio" no Finder.
- Aviso de "já baixado", com opção de baixar de novo.
- Recentes no popup e campo pra colar link fora do YouTube.
- Página de Opções: pastas (com seletor do macOS), pasta de cada botão, resolução, login do Chrome.
- yt-dlp nightly em binário próprio (`~/.caramujo/bin`). Atualiza no login e a cada 24 h; se falhar, tenta de novo em 30 min.
- Escada de tentativas contra 403: padrão, sem cache, yt-dlp novo, clientes alternativos do player, IPv4, login do Chrome. Lembra a que funcionou por 24 h.
- Botão Testar: diagnóstico real com relatório copiável.
- Erros classificados (sem internet, privado, indisponível, idade, disco cheio, 403, travou). Cada um com a ação certa em botão.
- Corrigido: "sem internet" aparecia como "vídeo privado ou restrição de idade".
- Corrigido: o auto-update podia não atualizar nada (variável do Homebrew) e uma falha de rede adiava a próxima tentativa por 24 h.
- Corrigido: aviso mentiroso de "Conectando no YouTube" enquanto o servidor atualizava.
- Download travado sem escrever por 3 min é encerrado. Antes ficava pendurado e bloqueava os seguintes.
- Servidor reiniciado no meio do download avisa e limpa os restos (`.part`, `.ytdl`).
- Progresso lido do yt-dlp com velocidade e tempo restante; barra de vídeo não trava mais em 45% quando o formato vem inteiro.
- Notificação em até 1 s com o popup fechado (antes: até 30 s).
- Segurança: ID fixo da extensão, validação do cabeçalho Host, pasta de destino só dentro do usuário, permissão `tabs` trocada por `activeTab`.
- Testes automáticos (52) e `CHANGELOG`.

**Como atualizar:** `instalar.sh` de novo, remover a extensão antiga e carregar a pasta `extensao/` (o ID mudou).

**Ficou pra depois:** recorte por trecho, BPM e tom no nome, playlist inteira, capa embutida no MP3, identidade visual do Caramujo, limpeza de "(Official Video)" do nome do arquivo.

## 3.0.0 (2026-10)

**Dor:** `HTTP Error 403: Forbidden` em quase todo download.

- Causa: yt-dlp congelado numa versão de 2025 (pip no Python 3.9 do macOS) e sem runtime JS pro desafio do player.
- yt-dlp, deno e ffmpeg passaram pro Homebrew. Auto-update no login, a cada 24 h e na falha.
- Progresso real lido do yt-dlp, download em segundo plano, notificação com o popup fechado, nome de arquivo com acento, bloqueio de clique duplo, log podado.

## 2.1.0 (2026-06-12)

**Dor:** a extração dentro da extensão morreu (o YouTube cifra o áudio e pede prova de que não é robô).

- Servidor local com yt-dlp e ffmpeg. MP3 real, MP4 em qualquer qualidade.
- Problemas que ficaram: barra de progresso falsa e popup preso em "baixando" quando o service worker morria.

## 1.1.0 (2026-06-12)

- Primeira versão: extensão pura, API interna do YouTube por 3 rotas, MP3 via lame.js e um agente de macOS que movia os arquivos de Downloads pras pastas de Music.
