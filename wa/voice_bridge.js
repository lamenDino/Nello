// A voice note may take longer than fetch's default response-header timeout.
const http = require('http');
const https = require('https');

function transcribeVoice(base, key, stream) {
  return new Promise((resolve, reject) => {
    const url = new URL('/voice', base);
    const transport = url.protocol === 'https:' ? https : http;
    const request = transport.request(url, {
      method: 'POST', headers: { 'content-type': 'application/octet-stream', 'X-Voice-Key': key },
    }, (response) => {
      let data = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        data += chunk;
        if (data.length > 100000) response.destroy(new Error('voice response too large'));
      });
      response.on('error', reject);
      response.on('end', () => {
        if (response.statusCode !== 200) return reject(new Error('voice bridge unavailable'));
        try { resolve(JSON.parse(data)); } catch (error) { reject(error); }
      });
    });
    request.setTimeout(1300000, () => request.destroy(new Error('voice timeout')));
    request.on('error', reject);
    stream.on('error', (error) => request.destroy(error));
    stream.pipe(request);
  });
}

module.exports = { transcribeVoice };
