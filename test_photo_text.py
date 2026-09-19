import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import core
import photo_text as pt


class DescriptionTests(unittest.IsolatedAsyncioTestCase):
    def test_whatsapp_long_photos_are_compact(self):
        description = ('Testo completo con emoji \U0001f600 & dettagli.\n' * 200) + '#finale'
        caption = core.build_caption({'type': 'carousel', 'files': ['photo.jpg']},
                                     'https://facebook.com/photo/?fbid=123', 'Nello',
                                     description, dialect='whatsapp', max_desc=1500)
        self.assertNotIn(description, caption)
        self.assertLess(len(caption), 800)
        self.assertNotIn('#finale', caption)
        parts = pt.split_text(caption)
        self.assertEqual(''.join(parts), caption)
        self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 3500 for p in parts))

    def test_telegram_full_text_html_and_emoji(self):
        description = ('<Testo> & \U0001f600\n' * 900) + 'FINE #tag'
        caption = core.build_caption({'type': 'carousel', 'files': ['photo.jpg']},
                                     'https://facebook.com/photo/?fbid=123', 'Nello', description)
        header, extra = pt.telegram_parts(caption)
        self.assertIn(description, ''.join(extra))
        self.assertLessEqual(len(pt.plain_text(header).encode('utf-16-le')) // 2, 1024)
        self.assertTrue(all(len(x.encode('utf-16-le')) // 2 <= 3500 for x in extra))

    def test_short_telegram_keeps_caption(self):
        self.assertEqual(pt.telegram_parts('<b>Breve</b>'), ('<b>Breve</b>', []))

    def test_utf8_api_chunks_lossless(self):
        original = 'Hello world! \U0001f600 ' * 300
        parts = pt.split_text(original, 500, encoding='utf-8', divisor=1)
        self.assertEqual(''.join(parts), original)
        self.assertTrue(all(len(x.encode()) <= 500 for x in parts))

    def test_language_detection(self):
        self.assertTrue(pt._is_english('Today we are sharing the full story behind this amazing photograph.'))
        self.assertFalse(pt._is_english('Solo un paio di anni fa ve lo sareste mai immaginato uno scontro politico tra questi due?'))

    async def test_italian_no_network(self):
        text = 'Questa descrizione italiana deve rimanere completa e invariata.'
        with patch.object(pt.aiohttp, 'ClientSession') as session:
            self.assertEqual(await pt.photo_description(text), text)
            session.assert_not_called()

    async def test_translation_failure_preserves_original(self):
        text = 'This is the complete original description of the photograph.'
        with patch.object(pt.aiohttp, 'ClientSession', side_effect=TimeoutError):
            self.assertEqual(await pt.photo_description(text), text)

    async def test_translation_and_cache(self):
        text = 'This photograph tells an amazing story.\n#photo https://example.com'
        response = MagicMock()
        response.json = AsyncMock(return_value={'responseStatus': 200, 'responseData':
                                               {'translatedText': 'Questa fotografia racconta una storia straordinaria.'}})
        response.__aenter__ = AsyncMock(return_value=response)
        session = MagicMock()
        session.get.return_value = response
        session.__aenter__ = AsyncMock(return_value=session)
        with patch.object(pt.aiohttp, 'ClientSession', return_value=session):
            result = await pt.photo_description(text)
            self.assertIn('Questa fotografia', result)
            self.assertTrue(result.endswith('\n#photo https://example.com'))
            self.assertEqual(await pt.photo_description(text), result)
            self.assertEqual(session.get.call_count, 1)


if __name__ == '__main__':
    unittest.main()
