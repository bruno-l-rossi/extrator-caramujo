<plano_extrator_caramujo versao_doc="1" data="2026-11-15" leitor="IA (Claude) em conversa futura" idioma_resposta="pt-BR">

<como_usar>
Guia de retomada e implementação. Leitor é IA, sem contexto prévio. Ordem de leitura: `<estado_atual>` → `<restricoes_ambiente>` → `<decisoes_abertas>` → fase pedida pelo Bruno.
Antes de qualquer tarefa: ler `ABOUT ME/` (about-me-pessoal é o perfil que vale aqui: projeto pessoal, rideblan / Caramujo Records), auditar texto pro Bruno contra `anti-ai-writing-style.md`, responder em pt-BR.
IDs são estáveis: achados `A-xx`, ações `Fn.m`, decisões `D-x`. Cite o ID ao reportar progresso. Ao concluir uma ação, atualizar `<registro_progresso>
Atualizar a cada sessão. Formato: `AAAA-MM-DD | ID | feito/pendente/bloqueado | nota`.
2026-11-15 | análise | feito | plano criado; nada implementado; v3 sem commit.
2026-11-16 | F0.1 | pendente | Bruno commita (git na VM deixa .lock). Comando entregue na conversa. Tag sugerida v4.0.0, não v3.0.0 (v3 e v4 vão no mesmo commit).
2026-11-16 | F0.2 | pendente | log real do Mac não lido. Substituído pelo botão "Testar" do popup (GET /diagnostico) e pelas linhas "falhou"/"ok:" do servidor.log. Pedir ao Bruno o relatório do Testar + `tail -100 ~/.caramujo/servidor.log` na 1ª conversa depois de instalar.
2026-11-16 | F0.3 | parcial | Decisões assumidas pelo palpite: D-2 WAV sim; D-3 H.264 até 1080p + opção máxima; D-4 fila sim; D-6 cookies por botão/opção, desligado. D-1, D-5, D-7, D-8 não perguntadas (D-5/D-8 são F4, fora do escopo pedido). F5.6 segue aberta (iCloud).
2026-11-16 | F0.4 | feito | CHANGELOG.md
2026-11-16 | F1.1-F1.9 | feito | classificar_erro (11 classes), update persistido e com retry em 30 min, estado "atualizando" visível, vigia de silêncio (180 s; 300 s convertendo) com killpg, /cancelar + botão, estado.json e retomada, laço de 1 s no service worker, progress-template (testado com yt-dlp 2026.10.21 contra servidor HTTP local), 52 testes.
2026-11-16 | F1.10 | feito (variante) | em vez de build.json gravado pelo instalador: BUILD no .py e BUILD_ESPERADO em comum.js, com teste que garante igualdade. Popup avisa quando diferem.
2026-11-16 | F2.1 | feito | binário yt_dlp_macos do repo nightly em ~/.caramujo/bin (instalar.sh baixa; servidor rebaixa se faltar). Não validado no Mac: tempo de partida do onefile e se o EJS vem embutido (a flag --remote-components ejs:github continua passando).
2026-11-16 | F2.2 | feito | escada: padrão, sem cache, yt-dlp novo, clientes android_vr/tv/web_safari, IPv4, cookies. Clientes são da pesquisa de 2026-11-16 e vivem em config.json (clientes_alternativos). Reconferir quando mudar.
2026-11-16 | F2.3 | feito | GET /diagnostico + botão Testar (usa "Me at the zoo").
2026-11-16 | F2.4 | feito (variante) | sample=WAV na taxa da fonte (sem resample); referencia=MP3 V2 (era V0); video=-S vcodec:h264,res:N; video_max=comportamento antigo. Sem capa embutida (risco de falha no pós-processo).
2026-11-16 | F2.5 | feito | origens.jsonl + xattr kMDItemWhereFroms (macOS, não testado) + --embed-metadata.
2026-11-16 | F2.6 | feito | duplicado por id+perfil+destino+arquivo existente; "Baixar de novo" manda forcar.
2026-11-16 | F2.7 | não feito | só se o Bruno reclamar do nome do arquivo.
2026-11-16 | F3.1 | feito | config.json, GET/POST /config (mescla), /escolher_pasta (osascript), página de opções.
2026-11-16 | F3.2 | feito | fila sequencial; /progresso devolve {ativo, fila, recentes}. SEM espelho dos campos antigos na raiz (popup e background migraram juntos).
2026-11-16 | F3.3 | feito | GET /historico + lista Recentes + campo de colar link.
2026-11-16 | F3.4 | feito | commands Alt+Shift+S/R/V (Option no Mac). Conferir se não colidem com algo.
2026-11-16 | F3.5 | feito | contextMenus em link e página.
2026-11-16 | F3.6 | feito (variante) | sem rota /info: miniatura vem do ID (i.ytimg.com), duração lida do <video> da aba via scripting, título da aba. Sem tamanho estimado.
2026-11-16 | F3.7 | feito | botões por tipo de erro (tentar, ligar login, diagnóstico, copiar comando).
2026-11-16 | F3.8 | não feito | identidade visual só se o Bruno pedir (e apontar o arquivo de identidade).
2026-11-16 | F5.1 | feito (variante) | ID fixo via key, Origin exata, Host validado. Sem token pro curl: pedido sem Origin segue liberado (só processo local alcança).
2026-11-16 | F5.2 | feito | tabs -> activeTab (+ scripting, contextMenus).
2026-11-16 | F5.3 | parcial | instalar.sh enxuto, bootout/bootstrap com fallback. Pedido do Bruno: não gastar tempo com o instalador.
2026-11-16 | F5.4-F5.5 | feito | poda de log a cada 5 min de loop (atômica), 1 linha "ok:" por download, README reescrito.
2026-11-16 | F5.6 | pendente | perguntar se Documents sincroniza com iCloud.
2026-11-16 | VALIDAÇÃO NO MAC | pendente | nada abaixo foi rodado no Mac: (1) instalar.sh do início ao fim; (2) servidor sobe e /status mostra build 2026-11-16.1; (3) extensão recarregada com o ID novo; (4) 1 sample WAV, 1 referência MP3, 1 vídeo H.264; (5) abrir o WAV no FL Studio e o MP4 no Final Cut; (6) fila com 3 itens + cancelar 1; (7) atalho e clique direito; (8) Testar; (9) seletor de pasta nas Opções; (10) matar o servidor (`launchctl kickstart -k gui/$(id -u)/com.caramujo.servidor`) no meio de um download e ver o aviso; (11) vídeo com restrição de idade + login do Chrome; (12) conferir se a escada realmente resolve um 403 quando ele aparecer.
</registro_progresso>

</plano_extrator_caramujo>
