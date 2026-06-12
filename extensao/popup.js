// Popup: identifica o vídeo da aba ativa e dispara o download no background.

const elTitulo = document.getElementById('titulo');
const elStatus = document.getElementById('status');
const btnMp3 = document.getElementById('btnMp3');
const btnMp4 = document.getElementById('btnMp4');
const selPasta = document.getElementById('pasta');

let videoId = null;

function setStatus(msg, cls = '') {
  elStatus.textContent = msg;
  elStatus.className = cls;
}

function extrairVideoId(url) {
  try {
    const u = new URL(url);
    if (!u.hostname.endsWith('youtube.com')) return null;
    if (u.pathname === '/watch') return u.searchParams.get('v');
    const m = u.pathname.match(/^\/(shorts|live)\/([\w-]{11})/);
    if (m) return m[2];
    return null;
  } catch {
    return null;
  }
}

async function init() {
  // Pasta salva da última vez
  const { pasta } = await chrome.storage.sync.get('pasta');
  if (pasta !== undefined) selPasta.value = pasta;
  selPasta.addEventListener('change', () => chrome.storage.sync.set({ pasta: selPasta.value }));

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  videoId = tab ? extrairVideoId(tab.url || '') : null;

  if (!videoId) {
    elTitulo.textContent = 'Nenhum vídeo do YouTube aberto nesta aba.';
    btnMp3.disabled = true;
    btnMp4.disabled = true;
    return;
  }
  elTitulo.textContent = tab.title.replace(/ - YouTube$/, '');
}

async function baixar(formato) {
  btnMp3.disabled = true;
  btnMp4.disabled = true;
  setStatus(formato === 'mp3' ? 'Preparando áudio…' : 'Preparando vídeo…');
  chrome.runtime.sendMessage({
    type: 'baixar',
    formato,
    videoId,
    pasta: selPasta.value
  });
}

btnMp3.addEventListener('click', () => baixar('mp3'));
btnMp4.addEventListener('click', () => baixar('mp4'));

// Progresso vindo do background/offscreen
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'progresso') setStatus(msg.texto);
  if (msg.type === 'concluido') {
    setStatus('Download iniciado. Confere a barra de downloads.', 'ok');
    btnMp3.disabled = false;
    btnMp4.disabled = false;
  }
  if (msg.type === 'erro') {
    setStatus(msg.texto, 'erro');
    btnMp3.disabled = false;
    btnMp4.disabled = false;
  }
});

init();
