import unittest
from core import short_url, build_caption


class ShortURLTests(unittest.TestCase):
    def test_content_routes(self):
        cases = {
            'https://www.instagram.com/reel/ABC_12/?igsh=long&igshid=123&utm_source=chat':
                'https://www.instagram.com/reel/ABC_12/',
            'https://m.facebook.com/photo.php?fbid=1594898782432817&set=a.123&type=3&mibextid=long':
                'https://www.facebook.com/photo/?fbid=1594898782432817',
            'https://www.facebook.com/watch/?v=123456&ref=sharing&rdid=long':
                'https://www.facebook.com/watch/?v=123456',
            'https://www.facebook.com/reel/123456?mibextid=long':
                'https://www.facebook.com/reel/123456/',
            'https://www.facebook.com/permalink.php?story_fbid=pfbidABC&id=123&ref=share':
                'https://www.facebook.com/permalink.php?story_fbid=pfbidABC&id=123',
            'https://www.tiktok.com/@someone/video/123456?_r=1&_t=long&share_app_id=123':
                'https://www.tiktok.com/@someone/video/123456',
            'https://vm.tiktok.com/ZN82Bwemk/?_r=1&_t=long':
                'https://vm.tiktok.com/ZN82Bwemk/',
            'https://www.youtube.com/watch?v=Pq2ArYdUzQo&si=long&feature=shared&t=12s':
                'https://youtu.be/Pq2ArYdUzQo?t=12s',
            'https://www.youtube.com/shorts/Pq2ArYdUzQo?si=long':
                'https://www.youtube.com/shorts/Pq2ArYdUzQo',
            'https://x.com/someone/status/123456?s=46&t=long':
                'https://x.com/someone/status/123456',
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(short_url(original), expected)
                self.assertEqual(short_url(expected), expected)

    def test_unknown_identifiers_and_signatures_preserved(self):
        for url in ('https://example.com/file?token=secret&id=123',
                    'https://facebook.com/unknown?id=123&key=abc',
                    'https://notinstagram.com/reel/ABC/?key=abc'):
            self.assertEqual(short_url(url), url)

    def test_all_caption_dialects(self):
        for dialect in ('html', 'whatsapp', 'discord'):
            caption = build_caption({'type': 'carousel', 'files': ['photo.jpg']},
                                    'https://facebook.com/photo/?fbid=123&set=a.456&mibextid=long',
                                    'Nello', 'Descrizione', dialect=dialect)
            self.assertIn('fbid=123', caption)
            self.assertNotIn('mibextid', caption)
            self.assertNotIn('set=', caption)
