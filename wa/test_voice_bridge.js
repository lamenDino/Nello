const assert = require('node:assert/strict');
const test = require('node:test');
const http = require('node:http');
const { Readable } = require('node:stream');
const { transcribeVoice } = require('./voice_bridge');

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
