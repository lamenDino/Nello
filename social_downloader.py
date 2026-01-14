#!/usr/bin/env python3
"""
Social Media Downloader v5.0
- VIDEO + CAROSELLO FOTO
- Instagram /p/ (carosello): scarica foto in modo robusto (yt-dlp playlist mode)
- Retry massimo 2 tentativi, poi STOP (silenzioso lato bot)
- Fix "File name too long": output corto (no title)
- TikTok /photo/: best-effort conversione in /video/
"""

import os
import re
import glob
import asyncio
import logging
import tempfile
from typing import Dict, Optional, List

import yt_dlp
import requests

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

        # cookies
        self.instagram_cookies = os.path.join(os.path.dirname(__file__), "cookies.txt")
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), "youtube_cookies.txt")

        self.user_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        # base ydl opts (video)
        self.base_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(self.temp_dir, "%(extractor)s_%(id)s.%(ext)s"),
            "paths": {"home": self.temp_dir},
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "max_filesize": 50 * 1024 * 1024,
            "retries": 2,
            "fragment_retries": 2,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "forceipv4": True,
            "restrictfilenames": True,
            "nopart": True,
        }

        self.max_retries = 2
        self.retry_delay = 2

    # -------------------------
    # helpers
    # -------------------------

    def get_random_user_agent(self) -> str:
        import random
        return random.choice(self.user_agents)

    def detect_platform(self, url: str) -> str:
        u = url.lower()
        if "tiktok" in u:
            return "tiktok"
        if "instagram" in u or "ig.tv" in u:
            return "instagram"
        if "facebook" in u or "fb." in u:
            return "facebook"
        if "youtube" in u or "youtu.be" in u:
            return "youtube"
        if "twitter" in u or "x.com" in u:
            return "twitter"
        return "unknown"

    def _rewrite_tiktok_photo_to_video(self, url: str) -> str:
        m = re.search(r"(https?://www\.tiktok\.com/@[^/]+)/(photo)/(\d+)", url)
        if not m:
            return url
        base = m.group(1)
        vid = m.group(3)
        return f"{base}/video/{vid}"

    def clean_url(self, url: str) -> str:
        url = (url or "").strip()

        # expand redirect
        if "facebook.com/share/" in url:
            try:
                r = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={"User-Agent": self.get_random_user_agent()},
                )
                url = r.url
            except Exception:
                pass

        if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
            try:
                r = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={"User-Agent": self.get_random_user_agent()},
                )
                url = r.url
            except Exception:
                pass

        # drop query (IG img_index ecc)
        if "?" in url:
            url = url.split("?", 1)[0]

        # best-effort TikTok photo -> video
        if "tiktok.com" in url.lower() and "/photo/" in url.lower():
            url = self._rewrite_tiktok_photo_to_video(url)

        return url

    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        opts = dict(self.base_opts)

        opts["http_headers"] = {
            "User-Agent": self.get_random_user_agent(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # cookies IG
        if "instagram" in url.lower() and os.path.exists(self.instagram_cookies):
            opts["cookiefile"] = self.instagram_cookies

        # cookies YT + headers
        if "youtube" in url.lower() or "youtu.be" in url.lower():
            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts["cookiefile"] = self.youtube_cookies
            opts["http_headers"].update({"Referer": "https://www.youtube.com/", "Origin": "https://www.youtube.com"})

        # headers FB
        if "facebook" in url.lower():
            opts["http_headers"].update({"Referer": "https://www.facebook.com/", "Origin": "https://www.facebook.com"})

        # headers TikTok
        if "tiktok" in url.lower():
            opts["http_headers"].update({"Referer": "https://www.tiktok.com/", "Origin": "https://www.tiktok.com"})

        return opts

    async def extract_info(self, url: str, attempt: int = 0) -> Optional[Dict]:
        """
        Metadata robusta. Per IG carosello può anche non avere formats video.
        """
        try:
            opts = self.get_ydl_opts(url, attempt)
            opts["skip_download"] = True
            opts.pop("format", None)
            opts["ignore_no_formats_error"] = True

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            return await loop.run_in_executor(None, _extract)

        except Exception as e:
            logger.error(f"Extract info attempt {attempt}: {str(e)[:220]}")
            return None

    async def download_with_ytdlp(self, url: str, attempt: int = 0) -> Optional[str]:
        """
        Download video classico
        """
        try:
            opts = self.get_ydl_opts(url, attempt)
            loop = asyncio.get_event_loop()

            def _download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                    info2 = ydl.extract_info(url, download=False)
                    return ydl.prepare_filename(info2)

            filename = await loop.run_in_executor(None, _download)

            if filename and os.path.exists(filename):
                return filename

            if filename:
                base = os.path.splitext(filename)[0]
                for ext in [".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv"]:
                    test_file = base + ext
                    if os.path.exists(test_file):
                        return test_file

            return None

        except Exception as e:
            logger.error(f"Download attempt {attempt}: {str(e)[:220]}")
            return None

    async def download_instagram_carousel(self, url: str, attempt: int = 0) -> List[str]:
        """
        Metodo robusto: usa yt-dlp per scaricare TUTTI gli item del post (foto/video).
        Noi poi filtriamo e teniamo solo le immagini.
        """
        opts = self.get_ydl_opts(url, attempt)

        # output corto e con index per playlist
        # %(id)s è corto e stabile, %(playlist_index)s evita sovrascritture
        opts["outtmpl"] = os.path.join(self.temp_dir, "ig_%(id)s_%(playlist_index)s.%(ext)s")
        opts["noplaylist"] = False
        opts["ignore_no_formats_error"] = True
        opts["quiet"] = True
        opts["no_warnings"] = True
        opts["max_filesize"] = 50 * 1024 * 1024

        loop = asyncio.get_event_loop()

        def _download_all():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        # prima di scaricare, pulisci eventuali vecchi file con stesso pattern
        # (evita di raccogliere roba vecchia)
        for f in glob.glob(os.path.join(self.temp_dir, "ig_*_*.*")):
            try:
                os.remove(f)
            except Exception:
                pass

        try:
            await loop.run_in_executor(None, _download_all)
        except Exception as e:
            logger.error(f"IG carousel download error: {str(e)[:220]}")
            return []

        # raccogli ciò che ha creato
        created = sorted(glob.glob(os.path.join(self.temp_dir, "ig_*_*.*")))

        # tieni SOLO immagini
        imgs = []
        for p in created:
            ext = os.path.splitext(p)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    imgs.append(p)
            else:
                # se yt-dlp ha scaricato anche un mp4 dentro al post, lo buttiamo
                try:
                    os.remove(p)
                except Exception:
                    pass

        return imgs

    # -------------------------
    # main
    # -------------------------

    async def download_video(self, url: str) -> Dict:
        clean_url = self.clean_url(url)
        platform = self.detect_platform(clean_url)

        for attempt in range(self.max_retries):
            try:
                info = await self.extract_info(clean_url, attempt)

                # se non riesce nemmeno a estrarre info -> retry / fail
                if not info:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return {"success": False}

                title = info.get("title") or "N/A"
                uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Sconosciuto"

                # ====== INSTAGRAM /p/ => SOLO carosello (NON provare video) ======
                if platform == "instagram" and "/p/" in clean_url.lower():
                    files = await self.download_instagram_carousel(clean_url, attempt)
                    if files:
                        return {
                            "success": True,
                            "type": "carousel",
                            "files": files,
                            "title": title,
                            "uploader": uploader,
                            "platform": platform,
                            "url": clean_url,
                        }

                    # se non ha scaricato foto, non provare a scaricare "video" (non esiste)
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return {"success": False}

                # ====== VIDEO (tutte le altre) ======
                file_path = await self.download_with_ytdlp(clean_url, attempt)
                if file_path and os.path.exists(file_path):
                    return {
                        "success": True,
                        "type": "video",
                        "file_path": file_path,
                        "title": title,
                        "uploader": uploader,
                        "duration": info.get("duration", 0) or 0,
                        "platform": platform,
                        "url": clean_url,
                    }

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue

                return {"success": False}

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)[:220]}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return {"success": False}
