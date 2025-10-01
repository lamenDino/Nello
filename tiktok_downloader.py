import os
import asyncio
import logging
import tempfile
import re
from typing import Dict, Optional
import yt_dlp
import requests

logger = logging.getLogger(__name__)

class TikTokDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

        # Configurazione yt-dlp
        self.ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'max_filesize': 50 * 1024 * 1024,  # 50MB max (limite Telegram)
        }

    async def download_video(self, url: str) -> Dict:
        try:
            clean_url = self.clean_tiktok_url(url)
            info = await self.extract_video_info(clean_url)
            if not info:
                return {'success': False, 'error': 'Impossibile ottenere informazioni sul video'}

            file_path = await self.download_with_ytdlp(clean_url)

            if file_path and os.path.exists(file_path):
                return {
                    'success': True,
                    'file_path': file_path,
                    'title': info.get('title', 'Video TikTok'),
                    'author': info.get('uploader', 'Sconosciuto'),
                    'duration': info.get('duration', 0),
                    'url': clean_url
                }
            else:
                return {'success': False, 'error': 'Download fallito'}
        except Exception as e:
            logger.error(f"Errore nel download di {url}: {str(e)}")
            return {'success': False, 'error': str(e)}

    async def extract_video_info(self, url: str) -> Optional[Dict]:
        try:
            ydl_opts_info = {**self.ydl_opts, 'skip_download': True}
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = await loop.run_in_executor(None, ydl.extract_info, url)
                return info
        except Exception as e:
            logger.error(f"Errore nell'estrazione info per {url}: {str(e)}")
            return None

    async def download_with_ytdlp(self, url: str) -> Optional[str]:
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                await loop.run_in_executor(None, ydl.download, [url])
                info = await loop.run_in_executor(None, ydl.extract_info, url)
                filename = ydl.prepare_filename(info)

                if os.path.exists(filename):
                    return filename

                base = os.path.splitext(filename)[0]
                for ext in ['.mp4', '.webm', '.mkv']:
                    test_file = base + ext
                    if os.path.exists(test_file):
                        return test_file

                return None
        except Exception as e:
            logger.error(f"Errore yt-dlp per {url}: {str(e)}")
            return None

    def clean_tiktok_url(self, url: str) -> str:
        url = url.strip()
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                url = response.url
            except:
                pass
        if '?' in url:
            url = url.split('?')[0]
        return url

    def is_valid_tiktok_url(self, url: str) -> bool:
        tiktok_patterns = [
            r'https?://(?:www\\.)?tiktok\\.com/@[\\w\\.-]+/video/\\d+',
            r'https?://vm\\.tiktok\\.com/[\\w\\d]+',
            r'https?://vt\\.tiktok\\.com/[\\w\\d]+',
            r'https?://m\\.tiktok\\.com/v/\\d+',
        ]
        import re
        for pattern in tiktok_patterns:
            if re.match(pattern, url):
                return True
        return False

    def cleanup_temp_files(self, max_age_hours: int = 1):
        import time
        current_time = time.time()
        for filename in os.listdir(self.temp_dir):
            if filename.startswith('TikTok') or filename.endswith('.mp4'):
                file_path = os.path.join(self.temp_dir, filename)
                file_age = current_time - os.path.getctime(file_path)
                if file_age > (max_age_hours * 3600):
                    try:
                        os.remove(file_path)
                        logger.info(f"File temporaneo rimosso: {filename}")
                    except:
                        pass
