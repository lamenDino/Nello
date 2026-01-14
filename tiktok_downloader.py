import os
import asyncio
import logging
import tempfile
from typing import Dict, Optional

import yt_dlp
import requests

logger = logging.getLogger(__name__)


class TikTokDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

        # Cookie dedicati TikTok (opzionale)
        self.tiktok_cookies = os.path.join(os.path.dirname(__file__), "tiktok_cookies.txt")

        self.user_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        self.ydl_opts = {
            "format": "best[ext=mp4]/best",
            # filename corto (evita Errno 36)
            "outtmpl": os.path.join(self.temp_dir, "tiktok_%(id)s.%(ext)s"),
            "paths": {"home": self.temp_dir},
            "quiet": True,
            "no_warnings": True,
            "extractaudio": False,
            "max_filesize": 50 * 1024 * 1024,

            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "forceipv4": True,
            "restrictfilenames": True,
            "nopart": True,

            "http_headers": {
                "User-Agent": self._ua(),
                "Referer": "https://www.tiktok.com/",
                "Origin": "https://www.tiktok.com",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

        if os.path.exists(self.tiktok_cookies):
            self.ydl_opts["cookiefile"] = self.tiktok_cookies

    def _ua(self) -> str:
        import random
        return random.choice(self.user_agents)

    async def download_video(self, url: str) -> Dict:
        try:
            clean_url = self.clean_tiktok_url(url)

            info = await self.extract_video_info(clean_url)
            if not info:
                return {"success": False, "error": "Impossibile ottenere informazioni sul video"}

            file_path = await self.download_with_ytdlp(clean_url)
            if file_path and os.path.exists(file_path):
                return {
                    "success": True,
                    "type": "video",
                    "file_path": file_path,
                    "title": info.get("title", "Video TikTok"),
                    "uploader": info.get("uploader", "Sconosciuto"),
                    "duration": info.get("duration", 0),
                    "url": clean_url,
                }

            return {"success": False, "error": "Download fallito"}

        except Exception as e:
            logger.error(f"Errore nel download di {url}: {str(e)[:200]}")
            return {"success": False, "error": str(e)}

    async def extract_video_info(self, url: str) -> Optional[Dict]:
        try:
            ydl_opts_info = {**self.ydl_opts, "skip_download": True}
            ydl_opts_info["http_headers"] = {**ydl_opts_info.get("http_headers", {}), "User-Agent": self._ua()}

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    return ydl.extract_info(url, download=False)

            return await loop.run_in_executor(None, _extract)

        except Exception as e:
            logger.error(f"Errore nell'estrazione info per {url}: {str(e)[:200]}")
            return None

    async def download_with_ytdlp(self, url: str) -> Optional[str]:
        try:
            opts = dict(self.ydl_opts)
            opts["http_headers"] = {**opts.get("http_headers", {}), "User-Agent": self._ua()}

            loop = asyncio.get_event_loop()

            def _download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                    info = ydl.extract_info(url, download=False)
                    return ydl.prepare_filename(info)

            filename = await loop.run_in_executor(None, _download)

            if filename and os.path.exists(filename):
                return filename

            if filename:
                base = os.path.splitext(filename)[0]
                for ext in [".mp4", ".webm", ".mkv"]:
                    test_file = base + ext
                    if os.path.exists(test_file):
                        return test_file

            return None

        except Exception as e:
            logger.error(f"Errore yt-dlp per {url}: {str(e)[:200]}")
            return None

    def clean_tiktok_url(self, url: str) -> str:
        url = url.strip()
        if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                url = response.url
            except Exception:
                pass
        if "?" in url:
            url = url.split("?")[0]
        return url
