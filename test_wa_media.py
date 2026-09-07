import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wa_media import prepare_video


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires FFmpeg')
class WhatsAppVideoTests(unittest.TestCase):
    def test_conversion_with_and_without_audio(self):
        for audio in (True, False):
            with self.subTest(audio=audio), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'source.mp4'
                cmd = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                       'testsrc=size=322x242:rate=24']
                if audio:
                    cmd += ['-f', 'lavfi', '-i', 'sine=frequency=440']
                cmd += ['-t', '0.5', '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p']
                if audio:
                    cmd += ['-c:a', 'aac']
                subprocess.run(cmd + [str(source)], check=True, capture_output=True)
                output = prepare_video(str(source))
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams',
                                        '-of', 'json', output], check=True, capture_output=True)
                streams = json.loads(probe.stdout)['streams']
                video = next(s for s in streams if s['codec_type'] == 'video')
                self.assertEqual(video['codec_name'], 'h264')
                self.assertEqual(video['pix_fmt'], 'yuv420p')
                self.assertEqual([s['codec_name'] for s in streams if s['codec_type'] == 'audio'],
                                 ['aac'] if audio else [])
                data = Path(output).read_bytes()
                self.assertLess(data.index(b'moov'), data.index(b'mdat'))
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', output,
                                '-f', 'null', '-'], check=True, capture_output=True)
                self.assertTrue(source.exists())

    def test_invalid_download_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'invalid.mp4'
            source.write_text('<html>Download failed</html>')
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_video(str(source))
            self.assertEqual(list(Path(directory).iterdir()), [source])


if __name__ == '__main__':
    unittest.main()
