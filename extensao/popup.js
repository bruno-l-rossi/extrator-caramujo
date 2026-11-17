// Popup do Extrator Caramujo (v4).
// Três botões por intenção (Sample, Referência, Vídeo). O estado mora no servidor:
// fechou e reabriu, continua igual.

import {
  BUILD_ESPERADO, CMD_INSTALAR, idDoVideo, urlLimpa, limparTitulo,
  pegar, enviar, fmtVelocidade, fmtTempo
} from './comum.js';

const $ = (id) => document.getElementById(id);
const S = { status: null, videoUrl: null, videoTitulo: '', timer: null, servidorOk: false };

// ---------------------------------------------------------------- helpers de tela --

function botao(texto, fn, forte = false) {
  const b = document.createElement('button');
  b.className = 'peq' + (forte ? ' forte' : '');
  b.textContent = texto;
  b.addEventListener('click', fn);
  return b;
}

function setAviso(texto, tipo = '', acaoTexto = '', acaoFn = null) {
  const el = $('aviso');
  el.replaceChildren();
  if (!texto) { el.style.display = 'none'; return; }
  el.className = tipo;
  el.style.display = 'block';
  el.append(texto);
  if (acaoTexto) {
    el.append(document.createElement('br'));
    el.append(botao(acaoTexto, acaoFn));
  }
}

function setStatus(msg, cls = '') {
  $('status').textContent = msg;
  $('status').className = cls;
}

function setAcoes(lista) {
  const el = $('acoes');
  el.replaceChildren();
  for (const a of lista) el.append(botao(a.texto, a.fn, a.forte));
}

function mostrarBarra(pct) {
  $('barraWrap').style.display = 'block';
  $('barra').style.width = Math.max(3, Math.min(100, pct || 0)).toFixed(0) + '%';
}

function esconderBarra() {
  $('barraWrap').style.display = 'none';
  $('barra').style.width = '0%';
}

function travarBotoes() {
  const livre = !!(S.videoUrl && S.servidorOk);
  document.querySelectorAll('[data-perfil]').forEach((b) => { b.disabled = !livre; });
}

async function copiar(texto, aviso) {
  try {
    await navigator.clipboard.writeText(texto);
    setStatus(aviso || 'Copiado.', 'ok');
  } catch {
    setStatus('Não consegui copiar. Seleciona e copia na mão: ' + texto, 'erro');
  }
}

const copiarInstalar = () => copiar(CMD_INSTALAR, 'Comando copiado. Cola no Terminal.');

function rotuloDestino(id) {
  const d = S.status && S.status.destinos.find((x) => x.id === id);
  return d ? d.rotulo : id || '';
}

function rotuloPerfil(id) {
  const p = S.status && S.status.perfis.find((x) => x.id === id);
  return p ? p.rotulo : id || '';
}

// ------------------------------------------------------------------ renderização --

function textoAtivo(j) {
  const pct = Math.round(j.pct || 0);
  if (j.estado === 'atualizando') return j.etapa || 'Atualizando o yt-dlp…';
  if (j.estado === 'convertendo') return 'Processando: ' + (j.etapa || 'convertendo') + '…';
  if (j.estado === 'baixando') {
    let t = `Baixando ${j.etapa || ''} · ${pct}%`;
    const v = fmtVelocidade(j.velocidade);
    if (v) t += ' · ' + v;
    if (j.eta) t += ' · falta ' + fmtTempo(j.eta);
    return t;
  }
  return j.tentativa > 1 ? `Tentando de novo (${j.estrategia})…` : 'Conectando no YouTube…';
}

function acoesDoErro(j) {
  const lista = [];
  const refazer = () => pedir({ url: j.url, perfil: j.perfil, destino: j.destino, titulo: j.titulo, forcar: true });
  if (j.acao === 'cookies') {
    lista.push({
      texto: 'Ligar login do Chrome e tentar de novo', forte: true,
      fn: async () => {
        const r = await enviar('/config', { cookies: true });
        if (!r || !r.ok) { setStatus((r && r.dados.erro) || 'Não consegui mudar a configuração.', 'erro'); return; }
        refazer();
      }
    });
  } else if (j.acao === 'tentar') {
    lista.push({ texto: 'Tentar de novo', forte: true, fn: refazer });
  } else if (j.acao === 'diagnostico') {
    lista.push({ texto: 'Rodar diagnóstico', forte: true, fn: diagnosticar });
    lista.push({ texto: 'Tentar de novo', fn: refazer });
  } else if (j.acao === 'instalar') {
    lista.push({ texto: 'Copiar comando de instalação', forte: true, fn: copiarInstalar });
  }
  return lista;
}

// Devolve true enquanto tem trabalho.
function renderizar(p) {
  const ativo = p.ativo;
  const fila = p.fila || [];

  const ul = $('fila');
  ul.replaceChildren();
  for (const j of fila) {
    const li = document.createElement('li');
    const t = document.createElement('span');
    t.className = 't';
    t.textContent = (j.titulo || j.url) + ' · na fila';
    const x = document.createElement('span');
    x.className = 'x';
    x.textContent = '✕';
    x.title = 'Tirar da fila';
    x.addEventListener('click', () => enviar('/cancelar', { id: j.id }));
    li.append(t, x);
    ul.append(li);
  }

  if (ativo) {
    $('statusTitulo').textContent = ativo.titulo || '';
    mostrarBarra(ativo.pct);
    setStatus(textoAtivo(ativo));
    setAcoes([{ texto: 'Cancelar', fn: () => enviar('/cancelar', { id: ativo.id }) }]);
    return true;
  }
  if (fila.length) {
    setStatus('Esperando a vez…');
    return true;
  }

  esconderBarra();
  $('statusTitulo').textContent = '';
  const r = (p.recentes || [])[0];
  if (r && r.fim && Date.now() / 1000 - r.fim < 90) {
    $('statusTitulo').textContent = r.titulo || '';
    if (r.estado === 'ok') {
      setStatus(r.texto || 'Pronto.', 'ok');
      setAcoes([{ texto: 'Mostrar no Finder', forte: true, fn: () => enviar('/mostrar', { id: r.id }) }]);
    } else if (r.estado === 'erro') {
      setStatus(r.texto || 'Falhou.', 'erro');
      setAcoes(acoesDoErro(r));
    } else {
      setStatus('Cancelado.');
      setAcoes([]);
    }
  } else {
    setStatus('');
    setAcoes([]);
  }
  return false;
}

function offline() {
  S.servidorOk = false;
  travarBotoes();
  esconderBarra();
  setAviso('Servidor local offline. Roda o instalar.sh e recarrega a extensão.', 'erro',
    'Copiar comando de instalação', copiarInstalar);
}

function acompanhar() {
  clearInterval(S.timer);
  const passo = async () => {
    const p = await pegar('/progresso');
    if (!p || p.ok === false) {
      clearInterval(S.timer);
      offline();
      return;
    }
    if (!renderizar(p)) {
      clearInterval(S.timer);
      carregarHistorico();
    }
  };
  passo();
  S.timer = setInterval(passo, 700);
}

async function carregarHistorico() {
  const h = await pegar('/historico?n=6');
  const ul = $('recentes');
  ul.replaceChildren();
  if (!h || !h.itens || !h.itens.length) { $('blocoRecentes').style.display = 'none'; return; }
  $('blocoRecentes').style.display = 'block';
  for (const e of h.itens) {
    const li = document.createElement('li');
    const t = document.createElement('span');
    t.className = 't';
    t.textContent = e.titulo || e.url;
    const sub = document.createElement('span');
    sub.className = 'sub';
    sub.textContent = `${rotuloPerfil(e.perfil)} · ${rotuloDestino(e.destino)} · ${(e.data || '').slice(0, 10)}${e.existe ? '' : ' · arquivo não está mais lá'}`;
    t.append(sub);
    li.append(t);
    if (e.existe) li.append(botao('Finder', () => enviar('/mostrar', { arquivo: e.arquivo })));
    if (e.url) li.append(botao('YouTube', () => chrome.tabs.create({ url: e.url })));
    ul.append(li);
  }
}

// ------------------------------------------------------------------------ ações --

async function pedir(corpo) {
  const r = await enviar('/baixar', corpo);
  if (!r) { offline(); return; }
  if (r.dados.codigo === 'origem') { setAviso(r.dados.erro, 'erro'); return; }
  if (!r.ok) { setStatus(r.dados.erro || 'Servidor respondeu HTTP ' + r.status, 'erro'); setAcoes([]); return; }
  if (r.dados.ja_existe) {
    setStatus('Já baixado: ' + (r.dados.titulo || 'esse vídeo'), 'ok');
    setAcoes([
      { texto: 'Mostrar no Finder', forte: true, fn: () => enviar('/mostrar', { arquivo: r.dados.arquivo }) },
      { texto: 'Baixar de novo', fn: () => pedir(Object.assign({}, corpo, { forcar: true })) }
    ]);
    return;
  }
  chrome.runtime.sendMessage({ type: 'acompanhar' }).catch(() => {});
  acompanhar();
}

function baixar(perfil) {
  if (!S.videoUrl) return;
  pedir({ url: S.videoUrl, perfil, destino: $('selDestino').value || undefined, titulo: S.videoTitulo });
}

async function diagnosticar() {
  const el = $('diag');
  el.style.display = 'block';
  el.textContent = 'Testando contra o YouTube… (até 2 min)';
  const d = await pegar('/diagnostico', 130000);
  if (!d) { el.textContent = 'O servidor não respondeu ao teste.'; return; }
  const texto = (d.ok ? 'OK: ' : 'FALHOU: ') + d.resumo + '\n\n' + (d.linhas || []).join('\n');
  el.textContent = texto;
  setAcoes([{ texto: 'Copiar relatório', forte: true, fn: () => copiar(texto, 'Relatório copiado.') }]);
}

async function lerDuracao(tabId) {
  try {
    const [r] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => { const v = document.querySelector('video'); return v && isFinite(v.duration) ? v.duration : null; }
    });
    return r ? r.result : null;
  } catch {
    return null;
  }
}

function aplicarVideo(url, titulo, duracao) {
  S.videoUrl = url;
  S.videoTitulo = titulo || '';
  const id = idDoVideo(url || '');
  const thumb = $('thumb');
  if (id) { thumb.src = `https://i.ytimg.com/vi/${id}/mqdefault.jpg`; thumb.style.display = ''; }
  else thumb.style.display = 'none';
  $('titulo').textContent = url ? (titulo || 'Vídeo do link colado') : 'Nenhum vídeo do YouTube nesta aba.';
  let meta = '';
  if (duracao) {
    meta = fmtTempo(duracao);
    if (duracao > 3600) meta += ' · vídeo longo, vai demorar';
  }
  $('meta').textContent = meta;
  travarBotoes();
}

// --------------------------------------------------------------------------- init --

async function init() {
  $('lnkOpcoes').addEventListener('click', () => chrome.runtime.openOptionsPage());
  $('lnkTestar').addEventListener('click', diagnosticar);
  document.querySelectorAll('[data-perfil]').forEach((b) => b.addEventListener('click', () => baixar(b.dataset.perfil)));
  $('inpUrl').addEventListener('input', () => aplicarVideo(urlLimpa($('inpUrl').value.trim()), '', null));

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = urlLimpa(tab && tab.url ? tab.url : '');
  aplicarVideo(url, url ? limparTitulo(tab.title) : '', null);
  if (!url) $('colar').style.display = 'block';

  const st = await pegar('/status');
  if (!st) { offline(); return; }
  if (st.ok === false) { setAviso(st.erro || 'O servidor recusou o pedido.', 'erro'); return; }
  S.status = st;
  S.servidorOk = true;

  $('versao').textContent = 'yt-dlp ' + (st.ytdlp_versao || '?') + (st.ytdlp_canal ? ' · ' + st.ytdlp_canal : '');
  for (const p of st.perfis) {
    const btn = document.querySelector(`.dl[data-perfil="${p.id}"]`);
    if (btn) btn.querySelector('small').textContent = `${p.sub.split(' ')[0]} · ${rotuloDestino(p.destino)}`;
  }
  const sel = $('selDestino');
  sel.replaceChildren(new Option('Padrão de cada botão', ''));
  for (const d of st.destinos) sel.append(new Option(d.rotulo, d.id));

  if ((st.versao_servidor || 0) < 4) {
    S.servidorOk = false;
    setAviso('O servidor instalado é de uma versão antiga. Roda o instalar.sh de novo.', 'erro',
      'Copiar comando de instalação', copiarInstalar);
  } else if (!st.ytdlp || !st.ffmpeg) {
    setAviso('Faltam ferramentas no servidor (yt-dlp ou ffmpeg). Roda o instalar.sh.', 'erro',
      'Copiar comando de instalação', copiarInstalar);
  } else if (!st.js) {
    setAviso('Falta o deno no servidor: o YouTube vai recusar (403). Roda o instalar.sh.', 'erro',
      'Copiar comando de instalação', copiarInstalar);
  } else if (st.build !== BUILD_ESPERADO) {
    setAviso('O servidor instalado é de outra versão (' + st.build + '). Roda o instalar.sh pra alinhar.', '',
      'Copiar comando de instalação', copiarInstalar);
  }
  travarBotoes();

  if (url && tab.id != null) {
    const dur = await lerDuracao(tab.id);
    if (dur) aplicarVideo(url, S.videoTitulo, dur);
  }
  acompanhar();
}

init();
