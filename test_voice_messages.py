import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import voice_messages as voice


class VoiceFrontendTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_reply_only_for_italian_and_keep_original(self):
        media = SimpleNamespace(file_size=100, duration=12, get_file=AsyncMock(
            return_value=SimpleNamespace(download_to_drive=AsyncMock())))
        message = SimpleNamespace(voice=media, audio=None, from_user=SimpleNamespace(is_bot=False),
                                  chat_id=5, message_id=8, reply_text=AsyncMock(), delete=AsyncMock())
        with patch('voice_messages.claim', return_value=True), patch('voice_messages.release'), \
             patch('voice_messages.transcribe_file', new=AsyncMock(return_value={'text': 'Ciao ragazzi.'})):
            await voice.telegram_voice(SimpleNamespace(effective_message=message), None)
        message.reply_text.assert_awaited_once_with('Trascrizione del vocale:\nCiao ragazzi.', parse_mode=None, do_quote=True)
        message.reply_text.reset_mock()
        with patch('voice_messages.claim', return_value=True), patch('voice_messages.release'), \
             patch('voice_messages.transcribe_file', new=AsyncMock(return_value={})):
            await voice.telegram_voice(SimpleNamespace(effective_message=message), None)
        message.reply_text.assert_not_awaited()
        message.delete.assert_not_awaited()

    def test_uncertain_voice_has_feedback_foreign_voice_is_ignored(self):
        self.assertTrue(voice.result_parts(voice.outcome({'success': True, 'skipped': 'uncertain_language'})))
        self.assertTrue(voice.result_parts(voice.outcome({'success': False, 'reason': 'recognition_failed'})))
        self.assertEqual(voice.result_parts(voice.outcome({'success': True, 'skipped': 'not_italian'})), [])

    def test_limits_deduplication_and_readable_parts(self):
        self.assertFalse(voice.eligible(9 * 1024 * 1024, 30))
        self.assertFalse(voice.eligible(100, 181))
        self.assertTrue(voice.eligible(100, 180))
        self.assertTrue(voice.claim('test-id'))
        try:
            self.assertFalse(voice.claim('test-id'))
        finally:
            voice.release()
        parts = voice.reply_parts('Ciao ragazzi. ' * 300, 1900)
        self.assertTrue(all(len(p) <= 1900 for p in parts))

    async def test_discord_voice_reply_without_mentions_or_foreign_reply(self):
        attachment = SimpleNamespace(id=7, size=100, duration=10, content_type='audio/ogg',
                                     is_voice_message=lambda: True, save=AsyncMock())
        message = SimpleNamespace(id=88, author=SimpleNamespace(bot=False),
                                  attachments=[attachment], reply=AsyncMock())
        with patch('voice_messages.claim', return_value=True), patch('voice_messages.release'), \
             patch('voice_messages.transcribe_file', new=AsyncMock(return_value={'text': 'Ciao a tutti.'})):
            await voice.discord_voice(message)
        self.assertEqual(message.reply.await_args.args[0], 'Trascrizione del vocale:\nCiao a tutti.')
        self.assertFalse(message.reply.await_args.kwargs['mention_author'])
        self.assertFalse(message.reply.await_args.kwargs['allowed_mentions'].everyone)
        message.reply.reset_mock()
        with patch('voice_messages.claim', return_value=True), patch('voice_messages.release'), \
             patch('voice_messages.transcribe_file', new=AsyncMock(return_value={})):
            await voice.discord_voice(message)
        message.reply.assert_not_awaited()

    async def test_remote_foreign_language_is_never_forwarded(self):
        import os
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        deleted = []
        async def health(request):
            return web.json_response({'status': 'ok'})
        async def upload(request):
            self.assertEqual(await request.read(), b'voice')
            return web.json_response({'id': request.match_info['ident']}, status=202)
        async def status(request):
            return web.json_response({'state': 'done', 'result': {'success': True, 'language': 'en', 'text': 'Hello'}})
        async def remove(request):
            deleted.append(request.match_info['ident'])
            return web.json_response({'ok': True})
        app = web.Application()
        app.add_routes([web.get('/healthz', health), web.post('/voice-jobs/{ident}', upload),
                        web.get('/jobs/{ident}', status), web.delete('/jobs/{ident}', remove)])
        async with TestClient(TestServer(app)) as client:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'audio'; path.write_bytes(b'voice')
                with patch.dict(os.environ, {'DOWNLOADER_URL': str(client.make_url('')).rstrip('/'), 'DOWNLOADER_TOKEN': 'test'}):
                    self.assertEqual(await voice.transcribe_file(path), {})
        self.assertEqual(len(deleted), 1)


if __name__ == '__main__':
    unittest.main()
