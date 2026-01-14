#!/usr/bin/env python3
"""
Social Media Downloader v4.0
- Supporto VIDEO + CAROSELLO FOTO
- Instagram / TikTok / Facebook carousel extraction
- Return standardizzato per bot Telegram
"""

import os
import asyncio
import logging
import tempfile
import subprocess
from typing import Dict, Optional, List

import yt_dlp
import requests

logger = logging.getLogger(__name__)

class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

        self.instagram_cookies = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')

        self.check_ytdlp_version()

        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1',
        ]

        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
        }

        self.max_retries = 3
        self.retry_delay = 2

    # -------------------------------------------------------------

    def check_ytdlp_version(self):
        try:
            subprocess.run(
                ['pip', 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                timeout=60
            )
        except Exception as e:
            logger.warning(f"yt-dlp update skipped: {e}")

    def get_random_user_agent(self) -> str:
        import random
        return random.choice(self.user_agents)

    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        opts = self.base_opts.copy()

        opts['http_headers'] = {
            'User-Agent': self.get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
        }

        if 'instagram' in url and os.path.exists(self.instagram_cookies):
            opts['cookiefile'] = self.instagram_cookies

        if ('youtube' in url or 'youtu.be' in url) and os.path.exists(self.youtube_cookies):
            opts['cookiefile'] = self.youtube_cookies

        return opts

    # -------------------------------------------------------------

    async def download_video(self, url: str) -> Dict:
        clean_url = self.clean_url(url)
        platform = self.detect_platform(clean_url)

        for attempt in range(self.max_retries):
            try:
                info = await self.extract_info(clean_url, attempt)
                if not info:
                    raise RuntimeError("info extraction failed")

                # 🔥 CAROSELLO (entries)
                if 'entries' in info:
                    image_files = await self.download_carousel(info)
                    if image_files:
                        return {
                            "success": True,
                            "type": "carousel",
                            "files": image_files,
                            "title": info.get("title", ""),
                            "uploader": info.get("uploader", "Sconosciuto"),
                            "platform": platform,
                            "url": clean_url
                        }

                # 🎥 VIDEO NORMALE
                video_path = await self.download_single(clean_url, attempt)
                if not video_path:
                    raise RuntimeError("download failed")

                return {
                    "success": True,
                    "type": "video",
                    "file_path": video_path,
                    "title": info.get("title", ""),
                    "uploader": info.get("uploader", "Sconosciuto"),
                    "platform": platform,
                    "url": clean_url
                }

            except Exception as e:
                logger.error(f"Tentativo {attempt + 1} fallito: {str(e)}")
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

        return {
            "success": False,
            "error": "❌ Download fallito dopo vari tentativi."
        }

    # -------------------------------------------------------------

    async def extract_info(self, url: str, attempt: int = 0) -> Optional[Dict]:
        opts = self.get_ydl_opts(url, attempt)
        opts['skip_download'] = True

        loop = asyncio.get_event_loop()

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.error(f"extract_info error: {e}")
            return None

    # -------------------------------------------------------------

    async def download_single(self, url: str, attempt: int = 0) -> Optional[str]:
        opts = self.get_ydl_opts(url, attempt)

        loop = asyncio.get_event_loop()

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
                info = ydl.extract_info(url, download=False)
                return ydl.prepare_filename(info)

        try:
            filename = await loop.run_in_executor(None, _download)
            return filename if os.path.exists(filename) else None
        except Exception as e:
            logger.error(f"download_single error: {e}")
            return None

    # -------------------------------------------------------------

    async def download_carousel(self, info: Dict) -> List[str]:
        files = []

        for entry in info.get("entries", []):
            if entry.get("ext") in ("jpg", "png", "webp"):
                url = entry.get("url")
                if not url:
                    continue

                filename = os.path.join(
                    self.temp_dir,
                    f"carousel_{entry.get('id')}.{entry.get('ext')}"
                )

                try:
                    r = requests.get(url, timeout=15)
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    files.append(filename)
                except Exception:
                    continue

        return files

    # -------------------------------------------------------------

    def clean_url(self, url: str) -> str:
        url = url.strip()
        if '?' in url:
            url = url.split('?')[0]
        return url

    def detect_platform(self, url: str) -> str:
        u = url.lower()
        if 'instagram' in u:
            return 'instagram'
        if 'tiktok' in u:
            return 'tiktok'
        if 'facebook' in u or 'fb.' in u:
            return 'facebook'
        if 'youtube' in u or 'youtu.be' in u:
            return 'youtube'
        return 'unknown'
