import tempfile
from pathlib import Path
from datetime import datetime, timezone
import unittest
from ranking_store import JsonRankingStore
from wa_ranking import current_period

class WhatsAppRankingTests(unittest.IsolatedAsyncioTestCase):
    def test_same_saturday_utc_schedule_as_telegram(self):
        before = datetime(2026, 9, 12, 19, 59, tzinfo=timezone.utc)
        after = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)
        self.assertNotEqual(current_period(before), current_period(after))
        self.assertEqual(current_period(after), current_period(datetime(2026, 9, 14, 12, tzinfo=timezone.utc)))

    async def test_group_isolation_persistence_ack_and_new_week_points(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'ranking.json')
            store = JsonRankingStore(path)
            await store.wa_group_ranking('1@g.us', 'week1', point=(11, 'Alice'))
            await store.wa_group_ranking('2@g.us', 'week1', point=(22, 'Bob'))
            messages = await store.wa_group_ranking('1@g.us', 'week2', 'Quote')
            self.assertEqual(len(messages), 1)
            self.assertIn('Alice', messages[0]['text'])
            self.assertNotIn('Bob', messages[0]['text'])
            store = JsonRankingStore(path)
            self.assertEqual(await store.wa_group_ranking('1@g.us', 'week2'), messages)
            await store.wa_group_ranking('1@g.us', 'week2', point=(33, 'Carol'))
            self.assertEqual(await store.wa_group_ranking('1@g.us', 'week2', ack=messages[0]['id']), [])
            self.assertEqual(store.data['wa_groups']['1@g.us']['weekly'], {'33': 1})
            self.assertEqual(store.data['wa_groups']['2@g.us']['weekly'], {'22': 1})

    async def test_telegram_reset_preserves_whatsapp_points(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JsonRankingStore(str(Path(folder) / 'ranking.json'))
            await store.add_point(1, 'Telegram')
            await store.add_point(2, 'WhatsApp', platform='wa')
            await store.wa_group_ranking('1@g.us', 'week1', point=(2, 'WhatsApp'))
            await store.reset_weekly(platform='tg')
            self.assertEqual(await store.get_board('weekly'), [])
            self.assertEqual(len(await store.get_board('weekly', platform='wa')), 1)
            self.assertEqual(store.data['wa_groups']['1@g.us']['weekly'], {'2': 1})

    async def test_empty_group_does_not_send_and_poll_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JsonRankingStore(str(Path(folder) / 'ranking.json'))
            self.assertEqual(await store.wa_group_ranking('1@g.us', 'week1'), [])
            self.assertEqual(await store.wa_group_ranking('1@g.us', 'week2'), [])
            from unittest.mock import patch
            with patch.object(store, '_save') as save:
                self.assertEqual(await store.wa_group_ranking('1@g.us', 'week2'), [])
                save.assert_not_called()

class WhatsAppRankingBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_sent_group_routes_to_durable_delivery_and_ack(self):
        from aiohttp.test_utils import TestClient, TestServer
        from types import SimpleNamespace
        from unittest.mock import patch
        import wa_bridge
        with tempfile.TemporaryDirectory() as folder:
            store = JsonRankingStore(str(Path(folder) / 'ranking.json'))
            ns = SimpleNamespace(ranking_store=store, aforismi=['Quote'],
                                 newly_earned=lambda *_: [], achievements={})
            with patch('social_downloader.SocialMediaDownloader'), patch('wa_bridge.current_period', return_value='week1'):
                client = TestClient(TestServer(wa_bridge.build_app(ns)))
                await client.start_server()
                try:
                    response = await client.post('/sent', json={'jid': '1@g.us', 'key': 'sent-message',
                        'user_id': '123', 'user_name': 'Alice'})
                    self.assertEqual(response.status, 200)
                    response = await client.post('/weekly-rankings', json={'groups': ['1@g.us', '2@g.us']})
                    self.assertEqual((await response.json())['messages'], [])
                    with patch('wa_bridge.current_period', return_value='week2'):
                        response = await client.post('/weekly-rankings', json={'groups': ['1@g.us', '2@g.us']})
                        messages = (await response.json())['messages']
                        self.assertEqual(len(messages), 1)
                        self.assertEqual(messages[0]['jid'], '1@g.us')
                        await client.post('/ranking-ack', json={'jid': '1@g.us', 'id': messages[0]['id']})
                        response = await client.post('/weekly-rankings', json={'groups': ['1@g.us']})
                        self.assertEqual((await response.json())['messages'], [])
                finally:
                    await client.close()
