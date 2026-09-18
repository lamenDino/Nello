import os
import unittest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from facebook_resolver import handler


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_validation_and_metadata_only(self):
        app = web.Application()
        app.router.add_get('/internal/facebook/{ident}', handler())
        async with TestClient(TestServer(app)) as client:
            with patch.dict(os.environ, {'DOWNLOADER_TOKEN': 'a' * 32}), patch('facebook_resolver.resolve', return_value=None) as resolve:
                self.assertEqual((await client.get('/internal/facebook/123456')).status, 401)
                headers = {'Authorization': 'Bearer ' + 'a' * 32}
                self.assertEqual((await client.get('/internal/facebook/evil', headers=headers)).status, 400)
                resolve.assert_not_called()
                r = await client.get('/internal/facebook/123456', headers=headers)
                self.assertEqual(await r.json(), {'id': '123456', 'media': None})
                resolve.assert_called_once_with('123456')
