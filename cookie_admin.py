"""Private admin controls for cookies owned by the remote downloader."""
import logging
import os
import time

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)
LABELS = {'instagram': 'Instagram', 'facebook': 'Facebook', 'youtube': 'YouTube', 'tiktok': 'TikTok'}
MAX_BYTES = 512 * 1024
STATES = {'present': 'cookie presenti (accesso non verificato)', 'missing': 'cookie mancanti',
          'expired': 'cookie di sessione scaduti', 'invalid': 'file non valido',
          'missing_session': 'cookie di accesso mancanti'}
ISSUES = {'session_rejected': 'sessione rifiutata: verifica il login e rinnova i cookie',
          'account_restricted': 'account limitato o bloccato dal social: apri il sito dal browser e completa la verifica o la richiesta di controllo',
          'rate_limited': 'il social limita le richieste: attendi prima di riprovare; non significa necessariamente che i cookie siano scaduti',
          'access_denied': 'il social rifiuta l’accesso dal server: verifica account e sessione dal browser; il motivo non è confermato',
          'login_required': 'accesso richiesto: cookie o limitazione del sito da verificare',
          'access_check': 'controllo anti-bot o verifica account: cookie non necessariamente scaduti'}


SOCIAL_URLS = {'instagram': 'https://www.instagram.com/', 'facebook': 'https://www.facebook.com/',
               'youtube': 'https://www.youtube.com/', 'tiktok': 'https://www.tiktok.com/'}


def keyboard(platform=None):
    platforms = [platform] if platform else list(LABELS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Aggiorna ' + LABELS[p], callback_data='cookies:' + p)] for p in platforms
    ] + ([[InlineKeyboardButton('Apri ' + LABELS[platform], url=SOCIAL_URLS[platform])]] if platform else [])
      + [[InlineKeyboardButton('Stato cookie', callback_data='cookies:status')]])


class CookieAdmin:
    def __init__(self, admin_id, store=None):
        self.admin_id = admin_id
        self.store = store
        self.pending = {}
        self.pasted = {}
        self.alerts = {}
        self.loaded = False

    async def allowed(self, update):
        admin = await self.admin_id()
        return bool(admin > 0 and update.effective_user and update.effective_chat
                    and update.effective_chat.type == 'private'
                    and update.effective_chat.id == admin and update.effective_user.id == admin)

    async def api(self, method='GET', platform=None, content=None):
        base = os.getenv('DOWNLOADER_URL', '').rstrip('/')
        token = os.getenv('DOWNLOADER_TOKEN', '')
        if not base or not token:
            raise RuntimeError('Downloader remoto non configurato.')
        path = '/admin/cookies' + ('/' + platform if platform else '')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=150),
                                        headers={'Authorization': 'Bearer ' + token}) as session:
            async with session.request(method, base + path,
                                       json={'content': content} if content is not None else None) as response:
                if response.content_type != 'application/json':
                    raise RuntimeError('Downloader in avvio o non raggiungibile. Riprova tra un minuto.')
                data = await response.json()
                if response.status != 200:
                    # Only our bounded API messages, never echo HTTP bodies or credentials.
                    raise RuntimeError(data.get('error', 'Downloader non disponibile.')[:240])
                return data

    async def show_status(self, message):
        try:
            data = await self.api()
            lines = ['Gestione cookie — solo amministratore']
            for platform, item in data['platforms'].items():
                if platform in LABELS:
                    state = ISSUES.get(item.get('issue')) or STATES.get(item.get('state'), 'da verificare')
                    lines.append(LABELS[platform] + ': ' + state)
            lines.append('\nGli aggiornamenti vengono salvati sul downloader e valgono per WhatsApp e Telegram.')
            await message.reply_text('\n'.join(lines), reply_markup=keyboard())
        except Exception:
            log.warning('Cookie status unavailable')
            await message.reply_text('Downloader non raggiungibile. Riprova tra un minuto.', reply_markup=keyboard())

    async def select(self, update, platform):
        self.pending[update.effective_user.id] = (platform, time.monotonic() + 1200)
        self.pasted.pop(update.effective_user.id, None)
        await update.effective_message.reply_text(
            'Aggiornamento ' + LABELS[platform] + '\nAccedi al sito dal browser, poi esporta soltanto '
            'i cookie di questa piattaforma in formato Netscape. Incolla qui il contenuto, anche in più messaggi, '
            'poi premi Salva cookie. Oppure invia il file .txt. Hai 20 minuti. '
            'Il file sarà salvato sul downloader, anche per i prossimi riavvii.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Annulla', callback_data='cookies:cancel')]]))

    async def command(self, update, context):
        if not await self.allowed(update):
            return
        platform = (context.args[0].lower() if context.args else '')
        if platform in LABELS:
            await self.select(update, platform)
        else:
            await self.show_status(update.effective_message)

    async def callback(self, update, context):
        query = update.callback_query
        if not await self.allowed(update):
            await query.answer('Riservato all’amministratore in chat privata.', show_alert=True)
            return
        await query.answer()
        action = query.data.removeprefix('cookies:')
        if action in LABELS:
            await self.select(update, action)
        elif action == 'cancel':
            self.pending.pop(update.effective_user.id, None)
            self.pasted.pop(update.effective_user.id, None)
            await update.effective_message.reply_text('Aggiornamento annullato.', reply_markup=keyboard())
        elif action == 'save':
            ident = update.effective_user.id
            pending = self.pending.get(ident)
            if not pending or time.monotonic() > pending[1]:
                self.pending.pop(ident, None)
                self.pasted.pop(ident, None)
                await update.effective_message.reply_text('Seleziona nuovamente la piattaforma.', reply_markup=keyboard())
            elif not self.pasted.get(ident):
                await update.effective_message.reply_text('Incolla prima il contenuto dei cookie.')
            else:
                await self.save_content(update, context, pending[0], '\n'.join(self.pasted[ident]))
        elif action == 'status':
            await self.show_status(update.effective_message)

    async def capture_text(self, update, context):
        """Consume private cookie messages before the download/logging handler."""
        if (not update.effective_user or update.effective_user.id not in self.pending
                or not update.effective_chat or update.effective_chat.type != 'private'):
            return
        if not await self.allowed(update):
            return
        ident = update.effective_user.id
        pending = self.pending.get(ident)
        if not pending:
            return
        from telegram.ext import ApplicationHandlerStop
        message = update.effective_message
        try:
            await message.delete()
        except Exception:
            pass
        if time.monotonic() > pending[1]:
            self.pending.pop(ident, None)
            self.pasted.pop(ident, None)
            await message.reply_text('Richiesta scaduta. Seleziona nuovamente la piattaforma.', reply_markup=keyboard())
            raise ApplicationHandlerStop
        content = (message.text or '').strip()
        if content.startswith('```') and content.endswith('```'):
            content = '\n'.join(content.splitlines()[1:-1])
        parts = self.pasted.setdefault(ident, [])
        if sum(len(part.encode('utf-8')) + 1 for part in parts) + len(content.encode('utf-8')) > MAX_BYTES:
            await message.reply_text('Limite di 512 KB superato. Annulla e riprova esportando solo la piattaforma selezionata.')
            raise ApplicationHandlerStop
        parts.append(content)
        await message.reply_text(
            'Contenuto ricevuto. Puoi incollare altre parti; quando hai finito premi Salva cookie.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('Salva cookie', callback_data='cookies:save')],
                [InlineKeyboardButton('Annulla', callback_data='cookies:cancel')]]))
        raise ApplicationHandlerStop

    async def document(self, update, context):
        if not await self.allowed(update):
            return
        ident = update.effective_user.id
        pending = self.pending.get(ident)
        if not pending:
            return
        platform, expires = pending
        message = update.effective_message
        if time.monotonic() > expires:
            self.pending.pop(ident, None)
            self.pasted.pop(ident, None)
            await message.reply_text('Richiesta scaduta. Seleziona nuovamente la piattaforma.', reply_markup=keyboard())
            return
        doc = message.document
        if not doc or not (doc.file_name or '').lower().endswith('.txt') or not doc.file_size or doc.file_size > MAX_BYTES:
            await message.reply_text('Invia un file .txt Netscape di massimo 512 KB. Puoi riprovare qui.')
            return
        try:
            file = await context.bot.get_file(doc.file_id)
            raw = await file.download_as_bytearray()
            if len(raw) > MAX_BYTES:
                raise ValueError()
            content = raw.decode('utf-8-sig')
        except Exception:
            await message.reply_text('File non leggibile. Riprova con un file .txt UTF-8.')
            return
        try:
            await message.delete()
        except Exception:
            pass
        await self.save_content(update, context, platform, content)

    async def save_content(self, update, context, platform, content):
        ident = update.effective_user.id
        message = update.effective_message
        try:
            await self.api('PUT', platform, content)
        except RuntimeError as exc:
            self.pasted.pop(ident, None)
            await message.reply_text(str(exc) + '\nIncolla nuovamente il contenuto completo oppure reinvia il file.')
            return
        except Exception:
            log.warning('Cookie upload unavailable: platform=%s', platform)
            await message.reply_text('Aggiornamento non confermato. Riprova tra un minuto reinviando il file.')
            return
        self.pending.pop(ident, None)
        self.pasted.pop(ident, None)
        self.alerts.pop(platform, None)
        if self.store:
            try:
                await self.store.set_cookie_alerts(self.alerts)
            except Exception:
                log.warning('Cookie alert reset persistence unavailable')
        await context.bot.send_message(ident, 'Cookie ' + LABELS[platform] + ' salvati sul downloader. '
                                       'Saranno usati dai prossimi download e conservati ai riavvii. '
                                       'Non devi aggiornarli sull’altro Render. L’accesso verrà verificato al prossimo download.',
                                       reply_markup=keyboard())

    async def check(self, context):
        for ident, (_, expires) in list(self.pending.items()):
            if time.monotonic() > expires:
                self.pending.pop(ident, None)
                self.pasted.pop(ident, None)
        admin = await self.admin_id()
        if admin <= 0:
            return  # Never fall back to a group ID.
        try:
            if self.store and not self.loaded:
                self.alerts = await self.store.get_cookie_alerts()
                self.loaded = True
            data = await self.api()
            now = time.time()
            for platform, item in data['platforms'].items():
                if platform not in LABELS:
                    continue
                issue = item.get('issue')
                state = item.get('state')
                reason = ISSUES.get(issue) or (STATES.get(state) if state in ('expired', 'invalid') else None)
                if not reason:
                    self.alerts.pop(platform, None)
                    continue
                fingerprint = f"{admin}:{item.get('version')}:{reason}"
                previous = self.alerts.get(platform)
                if previous and previous.get('fingerprint') == fingerprint and now - previous.get('sent_at', 0) < 86400:
                    continue
                await context.bot.send_message(
                    admin, '⚠️ ' + LABELS[platform] + ': ' + reason + '.\n'
                    'Accedi al sito dal browser e usa il pulsante per aggiornare i cookie se necessario. '
                    'Avviso privato; nessun messaggio viene inviato nei gruppi.', reply_markup=keyboard(platform))
                self.alerts[platform] = {'fingerprint': fingerprint, 'sent_at': now}
                if self.store:
                    await self.store.set_cookie_alerts(self.alerts)
        except Exception as exc:
            log.warning('Cookie admin monitor unavailable: %s', type(exc).__name__)
