// Peças compartilhadas entre o popup, o service worker e a página de opções.

export const SERVIDOR = 'http://127.0.0.1:8765';
// Tem que ser igual ao BUILD do servidor (tests/test_servidor.py confere).
export const BUILD_ESPERADO = '2026-11-16.1';
export const ATIVOS = ['preparando', 'atualizando', 'baixando', 'convertendo'];
export const CMD_INSTALAR =
  'bash "/Users/bruno-l-rossi/Documents/Claude Cowork/OUTPUTS/extrator-caramujo/servidor/instalar.sh"';

// Aceita watch, shorts, live, embed e youtu.be. Devolve o ID de 11 caracteres ou null.
export function idDoVideo(url) {
  try {
    const u = new URL(url);
    let id = null;
    if (u.hostname === 'youtu.be') id = u.pathname.slice(1, 12);
    else if (u.hostname === 'youtube.com' || u.hostname.endsWith('.youtube.com')) {
      if (u.pathname === '/watch') id = u.searchParams.get('v');
      else {
        const m = u.pathname.match(/^\/(shorts|live|embed)\/([\w-]{11})/);
        if (m) id = m[2];
      }
    }
    return id && /^[\w-]{11}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}

// Tira lista, índice e tempo: sobra só watch?v=ID.
export function urlLimpa(url) {
  const id = idDoVideo(url);
  return id ? 'https://www.youtube.com/watch?v=' + id : null;
}

export function limparTitulo(t) {
  return (t || '').replace(/^\(\d+\)\s*/, '').replace(/ - YouTube( Music)?$/, '').trim();
}

// null = o servidor não respondeu. Resposta com erro HTTP volta como {ok:false, ...}.
export async function pegar(rota, ms = 2500) {
  try {
    const r = await fetch(SERVIDOR + rota, { signal: AbortSignal.timeout(ms) });
    const dados = await r.json().catch(() => null);
    if (!r.ok) return Object.assign({ ok: false, http: r.status }, dados || {});
    return dados;
  } catch {
    return null;
  }
}

// null = o servidor não respondeu. Senão {ok, status, dados}.
export async function enviar(rota, corpo = {}, ms = 8000) {
  try {
    const r = await fetch(SERVIDOR + rota, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(ms)
    });
    const dados = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, dados };
  } catch {
    return null;
  }
}

export function fmtVelocidade(bps) {
  if (!bps || bps <= 0) return '';
  if (bps >= 1048576) return (bps / 1048576).toFixed(1).replace('.', ',') + ' MB/s';
  return Math.round(bps / 1024) + ' KB/s';
}

export function fmtTempo(seg) {
  if (seg == null || !isFinite(seg)) return '';
  seg = Math.round(seg);
  const h = Math.floor(seg / 3600);
  const m = Math.floor((seg % 3600) / 60);
  const s = String(seg % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}
