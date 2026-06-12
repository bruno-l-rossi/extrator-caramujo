// Service worker: repassa a URL do vídeo pro servidor local (yt-dlp + ffmpeg).
//
// v2.1: guarda o estado do download. Assim o popup pode fechar e reabrir sem
// perder o "está trabalhando", e a barra de progresso continua de onde estava.

const SERVIDOR = 'http://127.0.0.1:8765';
const CHAVE = 'estadoDownload';

// Estado: { ativo, formato, texto, inicio } ou { ativo:false, resultado, texto }
async function setEstado(estado) {
  await chrome.storage.local.set({ [CHAVE]: estado });
  // Avisa o popup, se estiver aberto. Se não estiver, o storage segura o estado.
  chrome.runtime.sendMessage({ type: 'estado', estado }).catch(() => {});
}

async function getEstado() {
  const r = await chrome.storage.local.get(CHAVE);
  return r[CHAVE] || { ativo: false };
}

async function baixar({ formato, url, pasta }) {
  await setEstado({
    ativo: true,
    formato,
    inicio: Date.now(),
    texto: formato === 'mp3'
      ? 'Baixando e convertendo áudio…'
      : 'Baixando vídeo…'
  });

  let resp;
  try {
    resp = await fetch(SERVIDOR + '/baixar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, formato, pasta })
    });
  } catch (e) {
    await setEstado({ ativo: false, resultado: 'erro', fim: Date.now(),
      texto: 'Não achei o servidor local. Ele está rodando? Confere o instalar.sh.' });
    return;
  }

  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok || !dados.ok) {
    await setEstado({ ativo: false, resultado: 'erro', fim: Date.now(),
      texto: dados.erro || ('Servidor respondeu HTTP ' + resp.status) });
    return;
  }
  await setEstado({ ativo: false, resultado: 'ok', fim: Date.now(),
    texto: 'Pronto. Arquivo salvo na pasta escolhida.' });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'baixar') {
    baixar(msg);
  }
  // Popup abriu e quer saber se tem algo rolando
  if (msg.type === 'consultarEstado') {
    getEstado().then(sendResponse);
    return true; // resposta assíncrona
  }
});
