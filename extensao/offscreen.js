// Offscreen: baixa o stream de áudio (AAC), decodifica pra PCM com WebAudio
// e converte pra MP3 192 kbps com lamejs. Roda fora do popup, então o
// download continua mesmo se o popup fechar.

function avisar(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}

// Baixa em pedaços de 9 MB (o googlevideo limita a velocidade de
// requisições muito grandes sem header de range).
async function baixarStream(url, tamanho) {
  const PEDACO = 9 * 1024 * 1024;
  if (!tamanho) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('Falha ao baixar o áudio (HTTP ' + resp.status + ').');
    return await resp.arrayBuffer();
  }
  const partes = [];
  for (let inicio = 0; inicio < tamanho; inicio += PEDACO) {
    const fim = Math.min(inicio + PEDACO - 1, tamanho - 1);
    const resp = await fetch(url + '&range=' + inicio + '-' + fim);
    if (!resp.ok) throw new Error('Falha ao baixar o áudio (HTTP ' + resp.status + ').');
    partes.push(new Uint8Array(await resp.arrayBuffer()));
    const pct = Math.round((fim / tamanho) * 100);
    avisar({ type: 'progresso', texto: 'Baixando áudio… ' + pct + '%' });
  }
  const total = partes.reduce((s, p) => s + p.length, 0);
  const junto = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) { junto.set(p, pos); pos += p.length; }
  return junto.buffer;
}

function floatParaInt16(canal) {
  const out = new Int16Array(canal.length);
  for (let i = 0; i < canal.length; i++) {
    const s = Math.max(-1, Math.min(1, canal[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function converterParaMp3(audioBuffer) {
  const canais = Math.min(audioBuffer.numberOfChannels, 2);
  const taxa = audioBuffer.sampleRate;
  const enc = new lamejs.Mp3Encoder(canais, taxa, 192);

  const esq = floatParaInt16(audioBuffer.getChannelData(0));
  const dir = canais === 2 ? floatParaInt16(audioBuffer.getChannelData(1)) : null;

  const BLOCO = 1152;
  const saida = [];
  for (let i = 0; i < esq.length; i += BLOCO) {
    const e = esq.subarray(i, i + BLOCO);
    const d = dir ? dir.subarray(i, i + BLOCO) : undefined;
    const buf = canais === 2 ? enc.encodeBuffer(e, d) : enc.encodeBuffer(e);
    if (buf.length) saida.push(new Uint8Array(buf));
  }
  const fim = enc.flush();
  if (fim.length) saida.push(new Uint8Array(fim));
  return new Blob(saida, { type: 'audio/mpeg' });
}

async function processar({ url, tamanho, arquivo }) {
  try {
    const bruto = await baixarStream(url, tamanho);

    avisar({ type: 'progresso', texto: 'Decodificando áudio…' });
    const ctx = new AudioContext();
    const audioBuffer = await ctx.decodeAudioData(bruto);
    await ctx.close();

    avisar({ type: 'progresso', texto: 'Convertendo pra MP3…' });
    const blob = converterParaMp3(audioBuffer);

    avisar({ type: 'mp3Pronto', blobUrl: URL.createObjectURL(blob), arquivo });
  } catch (e) {
    avisar({ type: 'mp3Erro', texto: 'Conversão falhou: ' + e.message });
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'converterMp3') processar(msg);
});
