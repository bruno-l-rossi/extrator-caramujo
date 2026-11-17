// Página de opções do Extrator Caramujo (v4). Lê e grava a config no servidor local.

import { pegar, enviar } from './comum.js';

const $ = (id) => document.getElementById(id);
let destinos = [];       // [{id, rotulo, caminho, novo?}]
let perfilDestino = {};  // {sample: 'samples', ...}
let perfis = [];         // [{id, rotulo, sub}]

function msg(texto, cls = '') {
  $('msg').textContent = texto;
  $('msg').className = cls;
}

function slug(texto) {
  const s = (texto || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24);
  return s || 'pasta';
}

function idLivre(rotulo, ignorar) {
  const base = slug(rotulo);
  let id = base;
  let n = 2;
  while (destinos.some((d) => d !== ignorar && d.id === id)) id = `${base}-${n++}`;
  return id;
}

function desenharPastas() {
  const box = $('pastas');
  box.replaceChildren();
  destinos.forEach((d, i) => {
    const l = document.createElement('div');
    l.className = 'linha';
    const rot = document.createElement('input');
    rot.type = 'text'; rot.className = 'rot'; rot.value = d.rotulo; rot.placeholder = 'Nome';
    rot.addEventListener('input', () => { d.rotulo = rot.value; desenharPerfis(); });
    const cam = document.createElement('input');
    cam.type = 'text'; cam.value = d.caminho; cam.placeholder = '/Users/você/Music/…';
    cam.addEventListener('input', () => { d.caminho = cam.value; });
    const esc = document.createElement('button');
    esc.textContent = 'Escolher…';
    esc.addEventListener('click', async () => {
      msg('Escolhe a pasta na janela que abriu no Mac…');
      const r = await enviar('/escolher_pasta', {}, 300000);
      if (!r) { msg('O servidor não respondeu.', 'erro'); return; }
      if (r.dados.ok) { d.caminho = r.dados.caminho; cam.value = d.caminho; msg(''); }
      else if (r.dados.cancelado) msg('');
      else msg(r.dados.erro || 'Não consegui abrir o seletor.', 'erro');
    });
    const del = document.createElement('button');
    del.textContent = '✕';
    del.title = 'Remover';
    del.disabled = destinos.length <= 1;
    del.addEventListener('click', () => { destinos.splice(i, 1); acertarPerfis(); desenharPastas(); desenharPerfis(); });
    l.append(rot, cam, esc, del);
    box.append(l);
  });
}

function acertarPerfis() {
  for (const p of perfis) {
    if (!destinos.some((d) => d.id === perfilDestino[p.id])) perfilDestino[p.id] = destinos[0].id;
  }
}

function desenharPerfis() {
  const box = $('perfis');
  box.replaceChildren();
  for (const p of perfis) {
    const l = document.createElement('div');
    l.className = 'linha';
    const lab = document.createElement('label');
    lab.textContent = `${p.rotulo} (${p.sub.split(' ')[0]}) salva em`;
    const sel = document.createElement('select');
    for (const d of destinos) sel.append(new Option(d.rotulo || d.id, d.id));
    sel.value = perfilDestino[p.id];
    sel.addEventListener('change', () => { perfilDestino[p.id] = sel.value; });
    l.append(lab, sel);
    box.append(l);
  }
}

async function carregar() {
  const r = await pegar('/config');
  if (!r || r.ok === false) {
    msg(r && r.erro ? r.erro : 'Servidor local offline. Roda o instalar.sh.', 'erro');
    return;
  }
  const { config, status } = r;
  destinos = config.destinos.map((d) => Object.assign({}, d));
  perfilDestino = Object.assign({}, config.perfil_destino);
  perfis = status.perfis;
  $('selRes').value = String(config.resolucao_max);
  $('chkCookies').checked = !!config.cookies;
  $('versao').textContent = 'versão ' + (status.ytdlp_versao || '?') + (status.ytdlp_canal ? ' (' + status.ytdlp_canal + ')' : '');
  desenharPastas();
  desenharPerfis();
}

$('btnAddPasta').addEventListener('click', () => {
  destinos.push({ id: idLivre('pasta'), rotulo: 'Nova pasta', caminho: '', novo: true });
  desenharPastas();
  desenharPerfis();
});

$('btnSalvar').addEventListener('click', async () => {
  for (const d of destinos) {
    if (!d.rotulo.trim()) { msg('Falta o nome de uma pasta.', 'erro'); return; }
    if (!d.caminho.trim()) { msg('Falta o caminho de "' + d.rotulo + '".', 'erro'); return; }
  }
  // pasta nova ganha um id a partir do nome; os botões que apontavam pro id provisório acompanham
  for (const d of destinos) {
    if (!d.novo) continue;
    const velho = d.id;
    d.id = idLivre(d.rotulo, d);
    for (const k of Object.keys(perfilDestino)) if (perfilDestino[k] === velho) perfilDestino[k] = d.id;
    delete d.novo;
  }
  acertarPerfis();
  const r = await enviar('/config', {
    destinos,
    perfil_destino: perfilDestino,
    resolucao_max: Number($('selRes').value),
    cookies: $('chkCookies').checked
  });
  if (!r) { msg('O servidor não respondeu.', 'erro'); return; }
  if (!r.ok) { msg(r.dados.erro || 'Não salvou.', 'erro'); return; }
  msg('Salvo.', 'ok');
  await carregar();
});

$('btnUpdate').addEventListener('click', async () => {
  const r = await enviar('/atualizar', {});
  const ok = !!(r && r.ok);
  msg(ok ? 'Atualizando em segundo plano. Confere a versão daqui a pouco.' : 'Não consegui pedir a atualização.', ok ? 'ok' : 'erro');
});

$('btnAtalhos').addEventListener('click', () => chrome.tabs.create({ url: 'chrome://extensions/shortcuts' }));

carregar();
