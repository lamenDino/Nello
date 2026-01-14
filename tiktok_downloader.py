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
        base_dir = os.path.dirname(__file__)
        self.cookiefile = os.path.join(base_dir, "ttcookies.txt")

        self.ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(self.temp_dir, "tiktok_%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extractaudio": False,
            "max_filesize": 50 * 1024 * 1024,
            "socket_timeout": 30,
            "retries": 2,
            "fragment_retries": 2,
            "restrictfilenames": True,
            "nopart": True,
        }

        if os.path.exists(self.cookiefile):
            self.ydl_opts["cookiefile"] = self.cookiefile

        self.ydl_opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": "https://www.tiktok.com/",
            "Origin": "https://www.tiktok.com",
        }

    def clean_tiktok_url(self, url: str) -> str:
        url = url.strip()

        if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
            try:
                r = requests.head(url, allow_redirects=True, timeout=10)
                url = r.url
            except Exception:
                pass

        if "?" in url:
            url = url.split("?", 1)[0]

        # best effort per /photo/
        if "/photo/" in url:
            import re
            m = re.search(r"(https?://www\.tiktok\.com/@[^/]+)/(photo)/(\d+)", url)
            if m:
                url = f"{m.group(1)}/video/{m.group(3)}"

        return url

    async def extract_video_info(self, url: str) -> Optional[Dict]:
        try:
            ydl_opts_info = {**self.ydl_opts, "skip_download": True}
            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    return ydl.extract_info(url, download=False)

            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.error(f"Errore estrazione info TikTok: {str(e)[:200]}")
            return None

    async def download_with_ytdlp(self, url: str) -> Optional[str]:
        try:
            loop = asyncio.get_event_loop()

            def _download():
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
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
            logger.error(f"Errore yt-dlp TikTok: {str(e)[:200]}")
            return None

    async def download_video(self, url: str) -> Dict:
        try:
            clean_url = self.clean_tiktok_url(url)
            info = await self.extract_video_info(clean_url)
            if not info:
                return {"success": False, "error": "Impossibile ottenere informazioni TikTok"}

            file_path = await self.download_with_ytdlp(clean_url)
            if file_path and os.path.exists(file_path):
                return {
                    "success": True,
                    "file_path": file_path,
                    "title": info.get("title", "Video TikTok"),
                    "uploader": info.get("uploader", "Sconosciuto"),
                    "duration": info.get("duration", 0),
                    "url": clean_url,
                }

            return {"success": False, "error": "Download fallito"}

        except Exception as e:
            logger.error(f"Errore download TikTok: {str(e)[:200]}")
            return {"success": False, "error": str(e)}
