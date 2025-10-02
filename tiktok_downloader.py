import os
import asyncio
import logging
import tempfile
from typing import Dict, Optional, List
import yt_dlp
import requests

logger = logging.getLogger(__name__)

class TikTokDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.ydl_opts = {
            'format': 'bestvideo+bestaudio/best/bestimage',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'max_filesize': 50 * 1024 * 1024,
            'cookiefile': os.path.join(os.path.dirname(__file__), 'cookies.txt')
        }

    async def download_video(self, url: str) -> Dict:
        try:
            clean_url = self.clean_tiktok_url(url)
            info = await self.extract_video_info(clean_url)
            if not info:
                return {'success': False, 'error': 'Impossibile ottenere informazioni sul video'}

            # yt-dlp può scaricare più file per post multipli (gallery)
            loop = asyncio.get_event_loop()
            files = []
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                await loop.run_in_executor(None, ydl.download, [clean_url])
                if 'entries' in info:  # gallery / carousel Instagram
                    for entry in info['entries']:
                        filename = ydl.prepare_filename(entry)
                        if os.path.exists(filename):
                            files.append(filename)
                else:
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        files.append(filename)
            return {
                'success': True if files else False,
                'files': files,
                'title': info.get('title', 'Post Instagram'),
                'uploader': info.get('uploader', 'Sconosciuto'),
                'url': clean_url
            }
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
