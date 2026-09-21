// A voice note may take longer than fetch's default response-header timeout.
const http = require('http');
const https = require('https');

function transcribeVoice(base, key, stream, onProgress) {
  return new Promise((resolve, reject) => {
    const url = new URL('/voice', base);
    const transport = url.protocol === 'https:' ? https : http;
    const request = transport.request(url, {
      method: 'POST', headers: { 'content-type': 'application/octet-stream', 'X-Voice-Key': key,
        ...(onProgress ? { accept: 'application/x-ndjson' } : {}) },
    }, async (response) => {
      try {
        if (response.statusCode !== 200) throw new Error('voice bridge unavailable');
        let data = '', final, received = 0;
        const streaming = (response.headers['content-type'] || '').includes('application/x-ndjson');
        response.setEncoding('utf8');
        for await (const chunk of response) {
          received += chunk.length;
          data += chunk;
          if (data.length > 100000 || received > 2000000) throw new Error('voice response too large');
          if (streaming) {
            let newline;
            while ((newline = data.indexOf('\n')) >= 0) {
              const line = data.slice(0, newline); data = data.slice(newline + 1);
              if (!line.trim()) continue;
              const event = JSON.parse(line);
              if (event.type === 'progress' && onProgress) {
                try { await onProgress(event); } catch (_) { /* Still deliver the final transcript. */ }
              } else if (event.type === 'done') final = event;
            }
          }
        }
        if (!streaming) return resolve(JSON.parse(data));
        if (!final) throw new Error('voice stream ended before completion');
        resolve(final);
      } catch (error) { response.destroy(); reject(error); }
    });
    request.setTimeout(1300000, () => request.destroy(new Error('voice timeout')));
    request.on('error', reject);
    stream.on('error', (error) => request.destroy(error));
    stream.pipe(request);
  });
}

function createVoiceReply(sock, jid, original) {
  let reply;
  async function update({ text }) {
    if (!text) return;
    if (reply) await sock.sendMessage(jid, { text, edit: reply.key });
    else reply = await sock.sendMessage(jid, { text }, { quoted: original });
  }
  async function finish(result) {
    const parts = [...(result.parts || [])];
    if (reply) {
      const text = parts.shift() || 'Trascrizione non completata; l’audio originale resta nella chat.';
      try { await update({ text }); }
      catch (_) { await sock.sendMessage(jid, { text }, { quoted: original }); }
    }
    for (const text of parts) await sock.sendMessage(jid, { text }, { quoted: original });
  }
  return { update, finish };
}

module.exports = { transcribeVoice, createVoiceReply };
