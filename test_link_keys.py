import unittest
from link_keys import link_key


class LinkKeyTests(unittest.TestCase):
    def test_photo_ids_never_share_cache(self):
        self.assertNotEqual(link_key('https://www.facebook.com/photo/?fbid=123'),
                            link_key('https://www.facebook.com/photo/?fbid=456'))
        self.assertNotEqual(link_key('https://www.facebook.com/photo/?fbid=123'), 'facebook.com/photo')

    def test_photo_variants_share_identity(self):
        self.assertEqual(link_key('https://www.facebook.com/photo/?fbid=123&set=a.45'),
                         link_key('https://m.facebook.com/photo.php?set=a.45&fbid=123'))

    def test_other_links_remain_compatible(self):
        self.assertEqual(link_key('https://www.instagram.com/reel/ABC/?tracking=1'), 'instagram.com/reel/abc')
        self.assertEqual(link_key('https://www.facebook.com/reel/123/'), 'facebook.com/reel/123')
