import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import voice_speakers as speakers


class SpeakerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.text = 'Ciao, come stai? Bene, grazie mille! Ci sentiamo domani.'
        self.words = [dict(word=w, start=i, end=i+.8) for i, w in enumerate(self.text.split())]
        self.turns = [[0, 2.9, 8], [3, 5.9, 2], [6, 8.9, 8]]

    def test_stable_numbering_by_first_appearance_and_returning_speaker(self):
        result = speakers.label_text(self.text, self.words, self.turns)
        self.assertEqual(result, 'Voce 1:\nCiao, come stai?\n\nVoce 2:\nBene, grazie mille!\n\nVoce 1:\nCi sentiamo domani.')

    def test_single_speaker_or_missing_alignment_keeps_plain_transcript(self):
        self.assertEqual(speakers.label_text(self.text, self.words, [[0, 9, 4]]), self.text)
        self.assertEqual(speakers.label_text(self.text, None, self.turns), self.text)
        self.words[0]['word'] = 'inventato'
        self.assertEqual(speakers.label_text(self.text, self.words, self.turns), self.text)

    def test_overlapping_voices_are_not_arbitrarily_assigned(self):
        overlapping = [[0, 9, 0], [0, 9, 1]]
        self.assertEqual(speakers.label_text(self.text, self.words, overlapping), self.text)
        self.assertEqual(speakers.label_text(self.text, self.words, [[0, float('nan'), 1]]), self.text)

    async def test_timeout_kills_worker_and_releases_single_worker_slot(self):
        proc = Mock(returncode=None)
        def kill():
            proc.returncode = -9
        proc.kill.side_effect = kill
        proc.wait = AsyncMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch('voice_speakers.Path.is_file', return_value=True), \
             patch('voice_speakers.memory_available', return_value=1024**3), \
             patch('voice_speakers.asyncio.create_subprocess_exec', new=AsyncMock(return_value=proc)):
            self.assertEqual(await speakers.diarize(Path(directory)/'audio.wav', timeout=0), [])
        proc.kill.assert_called_once()
        self.assertFalse(speakers._busy)

    async def test_concurrent_or_memory_limited_jobs_skip_optional_analysis(self):
        with patch('voice_speakers._busy', True), patch('voice_speakers.asyncio.create_subprocess_exec') as create:
            self.assertEqual(await speakers.diarize('unused'), [])
            create.assert_not_called()
        with patch('voice_speakers.memory_available', return_value=1), patch('voice_speakers.asyncio.create_subprocess_exec') as create:
            self.assertEqual(await speakers.diarize('unused'), [])
            create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
