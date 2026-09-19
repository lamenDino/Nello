import unittest
from caption_summary import summarize_photo
from core import build_caption


class SummaryTests(unittest.TestCase):
    def test_promotion_preserves_price_days_location_exclusions(self):
        text = ('FERMI TUTTI. QUESTA È GROSSA.\n' + 'Una serata davvero indimenticabile!\n' * 20
                + 'Arriva il nostro ALL YOU CAN EAT!\nOgni martedì e giovedì.\n'
                + '19,90€ a persona.\nBevande e coperto esclusi.\n'
                + 'STREAT FOOD — Via delle Torri 19, Grottaglie.\n#food #promo')
        summary = summarize_photo(text)
        for fact in ('ALL YOU CAN EAT', 'martedì e giovedì', '19,90€', 'Bevande e coperto esclusi', 'Via delle Torri 19'):
            self.assertIn(fact, summary)
        self.assertLessEqual(len(summary), 450)
        self.assertNotIn('#food', summary)

    def test_short_descriptions_unchanged(self):
        self.assertEqual(summarize_photo('Una bella foto #mare'), 'Una bella foto #mare')

    def test_only_whatsapp_and_discord_summarized(self):
        text = ('Descrizione completa.\n' * 60) + '#finale'
        for dialect in ('whatsapp', 'discord', 'html'):
            caption = build_caption({'type': 'carousel', 'files': ['photo.jpg']},
                                    'https://instagram.com/p/test/', 'Nello', text, dialect=dialect)
            if dialect == 'html':
                self.assertIn('#finale', caption)
            else:
                self.assertNotIn('#finale', caption)
                self.assertLess(len(caption), 800)
