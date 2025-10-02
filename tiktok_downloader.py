import os
import asyncio
import logging
import tempfile
from typing import Dict, Optional, List
import yt_dlp
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def insta_get_image_fallback(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            img_url = og_img['content']
            img_file = os.path.join(tempfile.gettempdir(), "insta_fallback.jpg")
            img_resp = requests.get(img_url, headers=headers)
            with open(img_file, "wb") as f:
                f.write(img_resp.content)
            return img_file
    except Exception as e:
        logger.error(f"Instagram fallback scraping error: {e}")
        pass
    return None

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
            files = []

            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                try:
                    await loop.run_in_executor(None, ydl.download, [clean_url])
                    if info and 'entries' in info and info['entries']:
                        for entry in info['entries']:
                            filename = ydl.prepare_filename(entry)
                            if os.path.exists(filename):
                                files.append(filename)
                    elif info and 'url' in info and info.get('ext'):
                        filename = ydl.prepare_filename(info)
                        if os.path.exists(filename):
                            files.append(filename)
                except Exception as e:
                    logger.warning(f"yt-dlp non ha trovato nè video nè immagini: {e}")
                    if "instagram.com" in clean_url:
                        img_file = insta_get_image_fallback(clean_url)
                        if img_file and os.path.exists(img_file):
                            files.append(img_file)
                            return {
                                'success': True,
                                'files': files,
                                'title': "Immagine Instagram (fallback)",
                                'uploader': 'Instagram Fallback',
                                'url': clean_url
                            }

            return {
                'success': True if files else False,
                'files': files,
                'title': info.get('title', 'Post Instagram') if info else 'Instagram',
                'uploader': info.get('uploader', 'Sconosciuto') if info else 'Instagram',
                'url': clean_url
            }
        except Exception as e:
            logger.error(f"Errore download Instagram fallback per {url}: {str(e)}")
            pass
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
            pass
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
