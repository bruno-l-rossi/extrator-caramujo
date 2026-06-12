// Service worker: busca os streams na API interna do YouTube e dispara os downloads.
// MP4 baixa direto. MP3 passa pelo offscreen.html (decodifica o áudio e converte com lamejs).

const API = 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false';

// Clientes da API interna, em ordem de tentativa. Alguns devolvem URL direta
// (sem cifra de assinatura); quando o YouTube muda as regras, outro da lista
// costuma continuar funcionando.
const CLIENTES = [
  {
    nome: 'IOS',
    context: {
      client: {
        clientName: 'IOS',
        clientVersion: '19.45.4',
        deviceMake: 'Apple',
        deviceModel: 'iPhone16,2',
        osName: 'iPhone',
        osVersion: '18.1.0.22B83',
        hl: 'pt-BR'
      }
    }
  },
  {
    nome: 'ANDROID',
    context: {
      client: {
        clientName: 'ANDROID',
        clientVersion: '19.44.38',
        androidSdkVersion: 35,
        osName: 'Android',
        osVersion: '15',
        hl: 'pt-BR'
      }
    }
  },
  {
    nome: 'TV_EMBEDDED',
    context: {
      client: {
        clientName: 'TVHTML5_SIMPLY_EMBEDDED_PLAYER',
        clientVersion: '2.0',
        hl: 'pt-BR'
      },
      thirdParty: { embedUrl: 'https://www.youtube.com' }
    }
  }
];

function avisar(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}

function nomeArquivo(titulo, ext) {
  const limpo = titulo
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120);
  return (limpo || 'youtube') + '.' + ext;
}

async function buscarStreams(videoId) {
  let ultimoErro = 'Nenhum cliente respondeu.';
  for (const cliente of CLIENTES) {
    try {
      const resp = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoId,
          context: cliente.context,
          contentCheckOk: true,
          racyCheckOk: true
        })
      });
      if (!resp.ok) { ultimoErro = 'HTTP ' + resp.status; continue; }
      const dados = await resp.json();

      const status = dados.playabilityStatus?.status;
      if (status !== 'OK') {
        ultimoErro = dados.playabilityStatus?.reason || ('Status: ' + status);
        continue;
      }

      const sd = dados.streamingData || {};
      // Só serve formato com URL direta (sem signatureCipher)
      const progressivos = (sd.formats || []).filter(f => f.url);
      const adaptativos = (sd.adaptiveFormats || []).filter(f => f.url);
      if (!progressivos.length && !adaptativos.length) {
        ultimoErro = 'Cliente ' + cliente.nome + ' só devolveu streams cifrados.';
        continue;
      }

      const titulo = dados.videoDetails?.title || 'youtube';
      return { progressivos, adaptativos, titulo };
    } catch (e) {
      ultimoErro = e.message;
    }
  }
  throw new Error('YouTube bloqueou a extração (' + ultimoErro + '). ' +
    'Isso acontece quando o YouTube muda a API; a extensão precisa de atualização.');
}

function melhorVideoMp4(progressivos) {
  // Progressivo = vídeo + áudio juntos, em MP4. Pega a maior resolução disponível.
  return progressivos
    .filter(f => (f.mimeType || '').includes('video/mp4'))
    .sort((a, b) => (b.height || 0) - (a.height || 0))[0] || null;
}

function melhorAudio(adaptativos) {
  // Prefere AAC (audio/mp4), que o Chrome decodifica nativamente. Maior bitrate primeiro.
  const audios = adaptativos.filter(f => (f.mimeType || '').startsWith('audio/'));
  const aac = audios.filter(f => (f.mimeType || '').includes('audio/mp4'));
  const lista = aac.length ? aac : audios;
  return lista.sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0))[0] || null;
}

async function garantirOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['BLOBS'],
    justification: 'Decodificar o áudio do vídeo e converter para MP3.'
  });
}

async function baixar({ formato, videoId, pasta }) {
  avisar({ type: 'progresso', texto: 'Buscando streams…' });
  const { progressivos, adaptativos, titulo } = await buscarStreams(videoId);

  if (formato === 'mp4') {
    const f = melhorVideoMp4(progressivos);
    if (!f) throw new Error('Nenhum stream MP4 com URL direta disponível pra esse vídeo.');
    await chrome.downloads.download({
      url: f.url,
      filename: pasta + nomeArquivo(titulo, 'mp4')
    });
    avisar({ type: 'concluido' });
    return;
  }

  // MP3
  const f = melhorAudio(adaptativos);
  if (!f) throw new Error('Nenhum stream de áudio com URL direta disponível.');
  await garantirOffscreen();
  avisar({ type: 'progresso', texto: 'Baixando áudio…' });
  chrome.runtime.sendMessage({
    type: 'converterMp3',
    url: f.url,
    tamanho: Number(f.contentLength) || 0,
    arquivo: pasta + nomeArquivo(titulo, 'mp3')
  });
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'baixar') {
    baixar(msg).catch(e => avisar({ type: 'erro', texto: e.message }));
  }
  // Offscreen terminou a conversão e mandou o blob URL
  if (msg.type === 'mp3Pronto') {
    chrome.downloads.download({ url: msg.blobUrl, filename: msg.arquivo })
      .then(() => avisar({ type: 'concluido' }))
      .catch(e => avisar({ type: 'erro', texto: e.message }));
  }
  if (msg.type === 'mp3Erro') {
    avisar({ type: 'erro', texto: msg.texto });
  }
});
