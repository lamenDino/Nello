import os
from pathlib import Path
import unittest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from remote_downloader import remote_download


class RestartTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, always_missing=False):
        submitted = []
        removed = []
        async def health(request):
            return web.json_response({'status': 'ok'})
        async def submit(request):
            submitted.append(await request.json())
            return web.json_response({'id': submitted[-1]['id']}, status=202)
        async def status(request):
            if always_missing or len(submitted) == 1:
                raise web.HTTPNotFound()
            return web.json_response({'state': 'done', 'result': {'success': True, 'type': 'video',
                'media': [{'index': 0, 'suffix': '.mp4', 'size': 5}]}})
        async def media(request):
            return web.Response(body=b'video')
        async def delete(request):
            removed.append(request.match_info['ident'])
            return web.json_response({'ok': True})
        app = web.Application()
        app.add_routes([web.get('/healthz', health), web.post('/jobs', submit),
                        web.get('/jobs/{ident}', status), web.get('/jobs/{ident}/files/{index}', media),
                        web.delete('/jobs/{ident}', delete)])
        async with TestClient(TestServer(app)) as client:
            with patch.dict(os.environ, {'DOWNLOADER_URL': str(client.make_url('')).rstrip('/'), 'DOWNLOADER_TOKEN': 'test'}):
                result = await remote_download('https://vm.tiktok.com/test/', target='telegram')
        self.assertEqual(len({b['id'] for b in submitted}), 1)
        self.assertEqual(len(removed), 1)
        if always_missing:
            self.assertFalse(result['success'])
            self.assertEqual(len(submitted), 3)
        else:
            self.assertTrue(result['success'])
            self.assertEqual(len(submitted), 2)
            path = Path(result['file_path'])
            try:
                self.assertEqual(path.read_bytes(), b'video')
            finally:
                path.unlink()

    async def test_restart_recovers_and_downloads_once(self):
        await self.scenario()

    async def test_repeated_missing_job_stops_at_retry_limit(self):
        await self.scenario(always_missing=True)
