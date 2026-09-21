const assert = require('node:assert/strict');
const test = require('node:test');
const http = require('node:http');
const { Readable } = require('node:stream');
const { transcribeVoice, createVoiceReply } = require('./voice_bridge');

test('streams audio to the bridge and receives transcript parts', async () => {
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    assert.equal(Buffer.concat(chunks).toString(), 'audio');
    assert.equal(req.headers['x-voice-key'], 'chat:message');
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ parts: ['Trascrizione del vocale:\nCiao.'] }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const result = await transcribeVoice(`http://127.0.0.1:${server.address().port}`, 'chat:message', Readable.from(['audio']));
    assert.deepEqual(result.parts, ['Trascrizione del vocale:\nCiao.']);
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('delivers fragmented progress before the server sends the final result', { timeout: 3000 }, async () => {
  let markSeen;
  const seen = new Promise(resolve => { markSeen = resolve; });
  const server = http.createServer(async (req, res) => {
    for await (const chunk of req) { /* drain uploaded audio */ }
    assert.equal(req.headers.accept, 'application/x-ndjson');
    res.setHeader('content-type', 'application/x-ndjson');
    const line = JSON.stringify({ type: 'progress', text: 'Ciao, è una prova.' }) + '\n';
    res.write(line.slice(0, 9)); res.write(line.slice(9));
    await seen;
    res.end(JSON.stringify({ type: 'done', parts: ['Testo finale.'] }) + '\n');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const result = await transcribeVoice(`http://127.0.0.1:${server.address().port}`, 'live', Readable.from(['audio']),
      async event => { assert.equal(event.text, 'Ciao, è una prova.'); markSeen(); });
    assert.deepEqual(result.parts, ['Testo finale.']);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test('edits only the bot reply, never the original audio', async () => {
  const original = { key: { id: 'original-audio' } };
  const sent = { key: { id: 'bot-transcript' } };
  const calls = [];
  const sock = { sendMessage: async (...args) => { calls.push(args); return sent; } };
  const live = createVoiceReply(sock, 'chat', original);
  await live.update({ text: 'Prima parte' });
  await live.update({ text: 'Prima e seconda parte' });
  await live.finish({ parts: ['Trascrizione finale'] });
  assert.equal(calls.length, 3);
  assert.equal(calls[0][2].quoted, original);
  assert.equal(calls[1][1].edit, sent.key);
  assert.equal(calls[2][1].edit, sent.key);
  assert.equal(calls[2][1].text, 'Trascrizione finale');
  assert.ok(calls.every(call => !call[1].delete));
});
