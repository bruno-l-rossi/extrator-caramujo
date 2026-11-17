// Service worker do Extrator Caramujo (v4).
//
// O download roda no servidor local. Aqui só acompanha: % no ícone, notificação
// quando cada item termina (mesmo com o popup fechado), atalhos de teclado e
// menu de clique direito. Enquanto houver item ativo ou na fila, um laço de 1 s
// consulta o servidor (cada chamada de API mantém o service worker vivo); o alarme
// de 30 s é a rede de segurança se o Chrome derrubar o worker.

import { ATIVOS, urlLimpa, limparTitulo, pegar, enviar } from './comum.js';

const ALARME = 'caramujo-acompanhar';
const ALARME_LIMPAR = 'caramujo-limpar';
const PERFIS_ATALHO = {
  'baixar-sample': 'sample',
  'baixar-referencia': 'referencia',
  'baixar-video': 'video'
};
const MENUS = [
  { id: 'sample', title: 'Caramujo: sample (WAV)' },
  { id: 'referencia', title: 'Caramujo: referência (MP3)' },
  { id: 'video', title: 'Caramujo: vídeo (MP4)' }
];

let rodando = false;
let tinhaAtivo = null; // null = ainda não li do storage

function badge(texto, cor) {
  chrome.action.setBadgeText({ text: texto });
  if (cor) chrome.action.setBadgeBackgroundColor({ color: cor });
}

function dormir(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function limparBadgeDepois() {
  setTimeout(() => badge(''), 15000);
  chrome.alarms.create(ALARME_LIMPAR, { delayInMinutes: 1 }); // se o worker morrer antes dos 15 s
}

function notificar(id, titulo, msg) {
  chrome.notifications.create(id, {
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title: 'Extrator Caramujo: ' + titulo,
    message: String(msg).slice(0, 250),
    priority: 1
  });
}

async function lerAvisados() {
  const { avisados } = await chrome.storage.local.get('avisados');
  return Array.isArray(avisados) ? avisados : [];
}

// Devolve true enquanto ainda tem trabalho (ativo ou fila).
async function tick() {
  const p = await pegar('/progresso', 3000);
  if (!p || p.ok === false) {
    if (tinhaAtivo === null) tinhaAtivo = !!(await chrome.storage.local.get('tinhaAtivo')).tinhaAtivo;
    if (tinhaAtivo) {
      tinhaAtivo = false;
      chrome.storage.local.set({ tinhaAtivo: false });
      badge('!', '#e8542f');
      notificar('queda', 'Falhou', 'Perdi contato com o servidor local durante o download.');
      limparBadgeDepois();
    } else {
      badge('');
    }
    return false;
  }

  const ativo = p.ativo;
  const fila = p.fila || [];
  const trabalhando = !!ativo || fila.length > 0;
  if (tinhaAtivo !== trabalhando) {
    tinhaAtivo = trabalhando;
    chrome.storage.local.set({ tinhaAtivo });
  }

  // Um aviso por item terminado, do mais antigo pro mais novo.
  const avisados = await lerAvisados();
  let mudou = false;
  let ultimo = null;
  for (const r of (p.recentes || []).slice().reverse()) {
    if (!r.fim || Date.now() / 1000 - r.fim > 600 || avisados.includes(r.id)) continue;
    avisados.push(r.id);
    mudou = true;
    if (r.estado === 'ok') {
      notificar(String(r.id), 'Pronto', (r.titulo || 'Download') + '\n' + (r.texto || ''));
      ultimo = 'ok';
    } else if (r.estado === 'erro') {
      notificar(String(r.id), 'Falhou', (r.titulo ? r.titulo + '\n' : '') + (r.texto || 'Erro no download.'));
      ultimo = 'erro';
    }
  }
  if (mudou) await chrome.storage.local.set({ avisados: avisados.slice(-60) });

  if (ativo && ATIVOS.includes(ativo.estado)) {
    const n = Math.round(ativo.pct || 0);
    badge(fila.length ? `${n}+${fila.length}` : `${n}%`, '#2f9e68');
  } else if (trabalhando) {
    badge('…', '#2f9e68');
  } else if (ultimo) {
    badge(ultimo === 'ok' ? 'OK' : '!', ultimo === 'ok' ? '#2f9e68' : '#e8542f');
    limparBadgeDepois();
  }
  return trabalhando;
}

async function ciclo() {
  if (rodando) return;
  rodando = true;
  chrome.alarms.create(ALARME, { periodInMinutes: 0.5 });
  try {
    for (let i = 0; i < 14400; i++) { // até 4 h
      if (!(await tick())) break;
      await dormir(1000);
    }
  } finally {
    rodando = false;
    chrome.alarms.clear(ALARME);
  }
}

// Usado pelo atalho de teclado e pelo menu de clique direito.
async function baixarDireto(urlBruta, perfil, tituloAba) {
  const url = urlLimpa(urlBruta || '');
  if (!url) {
    notificar('sem-video', 'Sem vídeo', 'Isso não é um link de vídeo do YouTube.');
    return;
  }
  const r = await enviar('/baixar', { url, perfil, titulo: limparTitulo(tituloAba) });
  if (!r) {
    notificar('offline', 'Servidor offline', 'Não achei o servidor local. Abre o popup pra ver o que fazer.');
    return;
  }
  if (r.dados.ja_existe) {
    notificar('ja-existe', 'Já baixado', (r.dados.titulo || 'Esse vídeo') + '\nAbre o popup se quiser baixar de novo.');
    return;
  }
  if (!r.ok) {
    notificar('erro-pedido', 'Falhou', r.dados.erro || 'Servidor respondeu HTTP ' + r.status);
    return;
  }
  badge('0%', '#2f9e68');
  ciclo();
}

function criarMenus() {
  chrome.contextMenus.removeAll(() => {
    for (const m of MENUS) {
      chrome.contextMenus.create({
        id: m.id,
        title: m.title,
        contexts: ['link', 'page'],
        documentUrlPatterns: ['https://www.youtube.com/*', 'https://m.youtube.com/*', 'https://music.youtube.com/*']
      });
    }
  });
}

chrome.runtime.onInstalled.addListener(() => {
  criarMenus();
  ciclo();
});
chrome.runtime.onStartup.addListener(() => ciclo());

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && (msg.type === 'acompanhar' || msg.type === 'tick')) ciclo();
});

chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === ALARME) ciclo();
  if (a.name === ALARME_LIMPAR && !rodando) badge('');
});

chrome.commands.onCommand.addListener(async (comando, tab) => {
  const perfil = PERFIS_ATALHO[comando];
  if (!perfil) return;
  if (!tab) [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  baixarDireto(tab && tab.url, perfil, tab && tab.title);
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const alvo = info.linkUrl || info.pageUrl || (tab && tab.url);
  baixarDireto(alvo, info.menuItemId, info.linkUrl ? '' : tab && tab.title);
});

chrome.notifications.onClicked.addListener((id) => {
  const n = Number(id);
  if (n) enviar('/mostrar', { id: n });
});
