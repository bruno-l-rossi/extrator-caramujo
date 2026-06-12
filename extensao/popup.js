// Popup: identifica o vídeo da aba, dispara o download e mostra o progresso.
// O estado real mora no background; o popup só reflete ele. Assim dá pra
// fechar e reabrir sem perder o "está trabalhando".

const SERVIDOR = 'http://127.0.0.1:8765';

const elTitulo = document.getElementById('titulo');
const elStatus = document.getElementById('status');
const barraWrap = document.getElementById('barraWrap');
const barra = document.getElementById('barra');
const btnMp3 = document.getElementById('btnMp3');
const btnMp4 = document.getElementById('btnMp4');
const selPasta = document.getElementById('pasta');

let videoUrl = null;
let timerBarra = null;

function setStatus(msg, cls = '') {
  elStatus.textContent = msg;
  elStatus.className = cls;
}

function ehVideoYoutube(url) {
  try {
    const u = new URL(url);
    if (!u.hostname.endsWith('youtube.com')) return false;
    if (u.pathname === '/watch' && u.searchParams.get('v')) return true;
    return /^\/(shorts|live)\/[\w-]{11}/.test(u.pathname);
  } catch {
    return false;
  }
}

// Barra fictícia: avança rápido no começo e desacelera perto do fim, sem nunca
// chegar a 100% sozinha (some quando o download termina de verdade). Usa o
// tempo decorrido desde o início, então ao reabrir o popup ela retoma na posição.
function animarBarra(inicioMs) {
  barraWrap.style.display = 'block';
  clearInterval(timerBarra);
  const passo = () => {
    const seg = (Date.now() - inicioMs) / 1000;
    // curva que tende a ~92% conforme o tempo passa (15s ~ 70%, 40s ~ 88%)
    const pct = Math.min(92, 100 * (1 - Math.exp(-seg / 18)));
    barra.style.width = pct.toFixed(0) + '%';
  };
  passo();
  timerBarra = setInterval(passo, 400);
}

function completarBarra() {
  clearInterval(timerBarra);
  barra.style.width = '100%';
  setTimeout(() => { barraWrap.style.display = 'none'; barra.style.width = '0%'; }, 600);
}

function pararBarra() {
  clearInterval(timerBarra);
  barraWrap.style.display = 'none';
  barra.style.width = '0%';
}

function travarBotoes(travar) {
  btnMp3.disabled = travar;
  btnMp4.disabled = travar;
}

// Reflete o estado vindo do background
function aplicarEstado(estado) {
  if (!estado) return;
  if (estado.ativo) {
    travarBotoes(true);
    setStatus(estado.texto || 'Trabalhando…');
    animarBarra(estado.inicio || Date.now());
  } else if (estado.resultado === 'ok') {
    travarBotoes(false);
    completarBarra();
    setStatus(estado.texto || 'Pronto.', 'ok');
  } else if (estado.resultado === 'erro') {
    travarBotoes(false);
    pararBarra();
    setStatus(estado.texto || 'Falhou.', 'erro');
  }
}

async function servidorVivo() {
  try {
    const r = await fetch(SERVIDOR + '/status', { signal: AbortSignal.timeout(1500) });
    return await r.json();
  } catch {
    return null;
  }
}

async function init() {
  const { pasta } = await chrome.storage.sync.get('pasta');
  if (pasta !== undefined) selPasta.value = pasta;
  selPasta.addEventListener('change', () => chrome.storage.sync.set({ pasta: selPasta.value }));

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab ? (tab.url || '') : '';

  if (!ehVideoYoutube(url)) {
    elTitulo.textContent = 'Nenhum vídeo do YouTube aberto nesta aba.';
    travarBotoes(true);
    return;
  }
  videoUrl = url;
  elTitulo.textContent = tab.title.replace(/ - YouTube$/, '');

  // Tem download rolando? (reabri o popup no meio)
  const estado = await chrome.runtime.sendMessage({ type: 'consultarEstado' });
  if (estado && estado.ativo) {
    aplicarEstado(estado);
    return; // não checa servidor; já está trabalhando
  }
  // Resultado recente (terminou nos últimos 60s enquanto o popup estava fechado)
  if (estado && estado.resultado && estado.fim && (Date.now() - estado.fim < 60000)) {
    aplicarEstado(estado);
    return;
  }

  // Servidor no ar?
  const st = await servidorVivo();
  if (!st) {
    setStatus('Servidor local offline. Roda o instalar.sh do servidor.', 'erro');
  } else if (!st.ytdlp || !st.ffmpeg) {
    setStatus('Faltam dependências no servidor (yt-dlp/ffmpeg). Roda o instalar.sh.', 'erro');
  }
}

function baixar(formato) {
  travarBotoes(true);
  setStatus(formato === 'mp3' ? 'Preparando áudio…' : 'Preparando vídeo…');
  animarBarra(Date.now());
  chrome.runtime.sendMessage({ type: 'baixar', formato, url: videoUrl, pasta: selPasta.value });
}

btnMp3.addEventListener('click', () => baixar('mp3'));
btnMp4.addEventListener('click', () => baixar('mp4'));

// Atualizações em tempo real enquanto o popup está aberto
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'estado') aplicarEstado(msg.estado);
});

init();
