import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import wave

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import remote_voice as remote
import voice_messages as voice


def transcript(language='italian', text='Ciao, domani passo alle 9.30. Non alle dieci.'):
    return {'language': language, 'segments': [
        {'start': 0, 'end': 3, 'text': text, 'no_speech_prob': .01, 'avg_logprob': -.1}]}


class RemoteVoiceTests(unittest.IsolatedAsyncioTestCase):
    def test_language_and_quality_filters(self):
        for language in ('english', 'french', 'german', 'en'):
            self.assertEqual(remote.interpret(transcript(language), 4)['skipped'], 'not_italian')
        self.assertEqual(remote.interpret(transcript(''), 4)['skipped'], 'uncertain_language')
        self.assertEqual(remote.interpret(transcript(text='il mio primo che è stato ' * 20), 4)['skipped'], 'no_clear_speech')
        data = transcript()
        data['segments'][0].update(no_speech_prob=.99, avg_logprob=-2)
        self.assertEqual(remote.interpret(data, 4)['skipped'], 'no_clear_speech')
        self.assertEqual(remote.interpret(transcript(), 4)['text'], 'Ciao, domani passo alle 9.30. Non alle dieci.')

    def test_paragraphs_preserve_times_names_and_negations(self):
        data = transcript(text='Ciao, non posso venire alle 9.30. Chiedi a Giulia.')
        data['segments'].append({'start': 5, 'end': 7, 'text': ' Un pò di tempo,qual’è il problema?'})
        self.assertEqual(remote.interpret(data, 8)['text'],
                         'Ciao, non posso venire alle 9.30. Chiedi a Giulia.\n\nUn po’ di tempo, qual è il problema?')

    async def test_upload_has_no_forced_language_and_cleans_temporary_audio(self):
        prepared = []
        async def prepare(source, output):
            prepared.append(output)
            output.write_bytes(b'wave data')
            return 4
        calls = []
        async def handler(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer test-key')
            fields = {}
            reader = await request.multipart()
            async for part in reader:
                fields[part.name] = await part.read()
            calls.append(fields)
            return web.json_response(transcript())
        app = web.Application()
        app.router.add_post('/transcribe', handler)
        async with TestClient(TestServer(app)) as client:
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'voice'; source.write_bytes(b'voice')
                with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'}), \
                     patch('remote_voice.ENDPOINT', str(client.make_url('/transcribe'))), \
                     patch('remote_voice.punctuate', new=AsyncMock(side_effect=lambda session, key, text: text)), \
                     patch('remote_voice.prepare_audio', side_effect=prepare):
                    result = await remote.transcribe(source)
                self.assertTrue(source.exists())
            self.assertTrue(result['success'])
            self.assertEqual(len(calls), 1)
            self.assertNotIn('language', calls[0])
            self.assertNotIn('prompt', calls[0])
            self.assertEqual(calls[0]['model'], b'whisper-large-v3')
            self.assertFalse(prepared[0].exists())

    async def test_http_quota_auth_redirect_and_failure_are_bounded(self):
        prepared = []
        async def prepare(source, output):
            prepared.append(output)
            output.write_bytes(b'wave data')
            return 4
        status = 429
        calls = []
        async def handler(request):
            calls.append(request.path)
            await request.read()
            return web.Response(status=status, headers={'Location': '/must-not-follow'})
        app = web.Application()
        app.router.add_post('/transcribe', handler)
        async with TestClient(TestServer(app)) as client:
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'voice'; source.write_bytes(b'voice')
                for status, expected in ((429, 'remote_rate_limit'), (401, 'remote_not_configured'),
                                         (503, 'remote_unavailable'), (307, 'remote_unavailable')):
                    with self.subTest(status=status), patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'}), \
                         patch('remote_voice.ENDPOINT', str(client.make_url('/transcribe'))), \
                         patch('remote_voice.prepare_audio', side_effect=prepare):
                        result = await remote.transcribe(source)
                    self.assertEqual(result['reason'], expected)
                    self.assertFalse(prepared[-1].exists())
                self.assertEqual(len(calls), 4)

    async def test_decode_checks_real_duration_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.wav'
            with wave.open(str(source), 'wb') as audio:
                audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                audio.writeframes(b'\0\0' * 32000)
            self.assertEqual(await remote.prepare_audio(source, Path(directory) / 'output.wav'), 2)
            with patch('remote_voice.MAX_SECONDS', 1):
                with self.assertRaisesRegex(ValueError, 'duration limit'):
                    await remote.prepare_audio(source, Path(directory) / 'long.wav')

    async def test_provider_errors_do_not_fall_back_to_nine_minute_local_job(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'voice'; source.write_bytes(b'voice')
            for reason in ('remote_rate_limit', 'remote_not_configured', 'remote_unavailable'):
                with self.subTest(reason=reason), patch.dict(os.environ, {'VOICE_TRANSCRIBER': 'groq'}), \
                     patch('remote_voice.transcribe', new=AsyncMock(return_value={'success': False, 'reason': reason})), \
                     patch('voice_messages.aiohttp.ClientSession') as local:
                    result = await voice.transcribe_file(source)
                    self.assertTrue(result.get('notice'))
                    local.assert_not_called()

    async def test_punctuation_cannot_change_words_negations_or_numeric_meaning(self):
        import aiohttp
        source = 'ciao non posso alle 9.30 domani chiedo a Giulia'
        candidate = ''
        status = 200
        async def handler(request):
            await request.read()
            return web.json_response({'choices': [{'finish_reason': 'stop', 'message': {'content': candidate}}]}, status=status)
        app = web.Application()
        app.router.add_post('/punctuate', handler)
        async with TestClient(TestServer(app)) as client, aiohttp.ClientSession() as session:
            with patch('remote_voice.TEXT_ENDPOINT', str(client.make_url('/punctuate'))):
                candidate = 'Ciao, non posso alle 9.30.\n\nDomani chiedo a Giulia.'
                self.assertEqual(await remote.punctuate(session, 'test-key', source), candidate)
                for candidate in ('Ciao, posso alle 9.30. Domani chiedo a Giulia.',
                                  'Ciao, non posso alle 9:30. Domani chiedo a Giulia.',
                                  'Ciao, non posso alle 9.30. Domani chiedo a Marta.'):
                    self.assertEqual(await remote.punctuate(session, 'test-key', source), source)
                status = 429
                self.assertEqual(await remote.punctuate(session, 'test-key', source), source)


if __name__ == '__main__':
    unittest.main()
