// Worker WhatsApp di Nello (Baileys).
//
// Si collega a WhatsApp come "dispositivo collegato" di un numero dedicato,
// ascolta i messaggi (gruppi e privati), riconosce i link supportati e li
// scarica/invia chiamando il bridge Python (http://127.0.0.1:8765), che riusa il
// downloader e lo store esistenti. Voti via reazioni native di WhatsApp.
//
// La sessione (credenziali) viene salvata sul bridge -> Firestore, così non serve
// riscansionare il QR a ogni deploy. Il QR per il PRIMO collegamento viene stampato
// nei log: scansionalo da WhatsApp -> Dispositivi collegati.
//
// Avviato da start.sh solo se WHATSAPP_ENABLED=1.

const fs = require('fs');
const makeWASocket = require('@whiskeysockets/baileys').default;
const {
  DisconnectReason,
  initAuthCreds,
  BufferJSON,
  proto,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcode = require('qrcode-terminal');

const BRIDGE = process.env.WA_BRIDGE_URL || 'http://127.0.0.1:8765';
const logger = pino({ level: process.env.WA_LOG_LEVEL || 'warn' });

// Domini supportati (allineato a is_supported_link lato Python)
const SUPPORTED = [
  'tiktok.com', 'instagram.com', 'facebook.com', 'fb.watch',
  'youtube.com', 'youtu.be', 'twitter.com', 'x.com',
  'reddit.com', 'redd.it', 'twitch.tv',
];
const isSupported = (u) => /^https?:\/\//i.test(u) && SUPPORTED.some((d) => u.includes(d));

// id numerico da un JID WhatsApp (es. "39333...@s.whatsapp.net" -> "39333...")
const numId = (jid) => {
  const m = String(jid || '').split('@')[0].split(':')[0].match(/\d+/);
  return m ? m[0] : '0';
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function bridge(path, opts) {
  const res = await fetch(BRIDGE + path, opts);
  return res.json();
}

async function waitForBridge() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(BRIDGE + '/ping');
      if (r.ok) return true;
    } catch (e) { /* non ancora pronto */ }
    await sleep(1000);
  }
  return false;
}

// --- Auth state persistito sul bridge (Firestore) ---
async function useRemoteAuthState() {
  let stored = null;
  try {
    const r = await bridge('/authstate');
    if (r && r.blob) stored = JSON.parse(r.blob, BufferJSON.reviver);
  } catch (e) {
    console.log('WA: impossibile caricare la sessione:', e.message);
  }
  const creds = (stored && stored.creds) || initAuthCreds();
  const keys = (stored && stored.keys) || {};

  let saveTimer = null;
  const flush = async () => {
    saveTimer = null;
    try {
      const blob = JSON.stringify({ creds, keys }, BufferJSON.replacer);
      await bridge('/authstate', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ blob }),
      });
    } catch (e) {
      console.log('WA: salvataggio sessione fallito:', e.message);
    }
  };
  // debounce: evita una scrittura Firestore a ogni singolo update di chiave
  const save = () => { if (!saveTimer) saveTimer = setTimeout(flush, 1500); };

  const state = {
    creds,
    keys: {
      get: (type, ids) => {
        const data = {};
        for (const id of ids) {
          let value = keys[`${type}-${id}`];
          if (type === 'app-state-sync-key' && value) {
            value = proto.Message.AppStateSyncKeyData.fromObject(value);
          }
          data[id] = value;
        }
        return data;
      },
      set: (data) => {
        for (const type in data) {
          for (const id in data[type]) {
            const value = data[type][id];
            const k = `${type}-${id}`;
            if (value) keys[k] = value; else delete keys[k];
          }
        }
        save();
      },
    },
  };
  return { state, saveCreds: save };
}

async function handleMessages(sock, upsert) {
  if (upsert.type !== 'notify') return;
  for (const m of upsert.messages) {
    try {
      if (!m.message || m.key.fromMe) continue;
      const jid = m.key.remoteJid;
      if (!jid || jid === 'status@broadcast') continue;

      // --- Reazione (voto) ---
      const rm = m.message.reactionMessage;
      if (rm) {
        const targetId = rm.key && rm.key.id;
        if (!targetId) continue;
        const voter = numId(m.key.participant || jid);
        const emoji = rm.text || '';
        try {
          const res = await bridge('/react', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ key: `wa:${targetId}`, user_id: voter, emoji }),
          });
          if (res && res.ok && res.announce) await sock.sendMessage(jid, { text: res.announce });
          if (res && res.ok && res.voter_ach) await sock.sendMessage(jid, { text: `🎉 ${res.voter_ach}` });
        } catch (e) { /* ignora */ }
        continue;
      }

      // --- Testo / link ---
      const text = m.message.conversation
        || (m.message.extendedTextMessage && m.message.extendedTextMessage.text)
        || '';
      if (!text) continue;
      const urls = text.split(/\s+/).map((t) => t.replace(/[<>]/g, '')).filter(isSupported);
      if (!urls.length) continue;

      const ownerJid = m.key.participant || jid;
      const ownerId = numId(ownerJid);
      const ownerName = m.pushName || 'Utente';

      for (const url of urls) {
        try {
          await sock.sendPresenceUpdate('composing', jid).catch(() => {});
          const info = await bridge('/download', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ url, sender_name: ownerName }),
          });

          if (!info.success) {
            if (info.skip_long) continue; // YouTube troppo lungo: lascia il link
            if (info.too_big) { await sock.sendMessage(jid, { text: info.caption }); continue; }
            await sock.sendMessage(jid, { text: `😵 Non riesco a scaricarlo.\n${info.error || ''}\n${url}` });
            continue;
          }

          const files = info.files || [];
          let voteKey = null;
          for (let i = 0; i < files.length; i++) {
            const f = files[i];
            let buf;
            try { buf = fs.readFileSync(f.path); } catch (e) { continue; }
            const caption = i === 0 ? info.caption : undefined;
            const payload = f.video ? { video: buf, caption } : { image: buf, caption };
            const sent = await sock.sendMessage(jid, payload);
            if (i === 0 && sent && sent.key) voteKey = `wa:${sent.key.id}`;
          }
          // pulizia file (Node e Python condividono il filesystem)
          for (const f of files) { try { fs.unlinkSync(f.path); } catch (e) { /* */ } }

          // punto in classifica + record voto + achievement
          try {
            const res = await bridge('/sent', {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({ url, user_id: ownerId, user_name: ownerName, key: voteKey }),
            });
            if (res && Array.isArray(res.achievements)) {
              for (const a of res.achievements) {
                await sock.sendMessage(jid, { text: `🎉 *${ownerName}* ha sbloccato un achievement!\n${a}` });
              }
            }
          } catch (e) { /* ignora */ }
        } catch (e) {
          console.log('WA: errore su', url, '-', e.message);
        }
      }
    } catch (e) {
      console.log('WA: errore messaggio:', e.message);
    }
  }
}

async function start() {
  const { state, saveCreds } = await useRemoteAuthState();
  let version;
  try { ({ version } = await fetchLatestBaileysVersion()); } catch (e) { /* default */ }

  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      console.log('\n================ WHATSAPP QR ================');
      console.log('Apri WhatsApp -> Dispositivi collegati -> Collega un dispositivo e scansiona:');
      qrcode.generate(qr, { small: true });
      console.log('============================================\n');
    }
    if (connection === 'open') {
      console.log('WA: connesso a WhatsApp ✅');
    } else if (connection === 'close') {
      const code = lastDisconnect && lastDisconnect.error
        && lastDisconnect.error.output && lastDisconnect.error.output.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      console.log('WA: connessione chiusa (code', code, ') - reconnect:', !loggedOut);
      if (!loggedOut) setTimeout(() => start().catch((e) => console.log('WA restart err', e.message)), 3000);
      else console.log('WA: sessione terminata (logout). Serve riscansionare il QR.');
    }
  });

  sock.ev.on('messages.upsert', (upsert) => {
    handleMessages(sock, upsert).catch((e) => console.log('WA upsert err:', e.message));
  });
}

(async () => {
  if (process.env.WHATSAPP_ENABLED !== '1') {
    console.log('WA: WHATSAPP_ENABLED non attivo, worker non avviato.');
    return;
  }
  console.log('WA: attendo il bridge Python su', BRIDGE, '...');
  const ok = await waitForBridge();
  if (!ok) { console.log('WA: bridge non raggiungibile, esco.'); process.exit(1); }
  console.log('WA: bridge pronto, avvio connessione WhatsApp...');
  start().catch((e) => console.log('WA: errore avvio:', e.message));
})();
