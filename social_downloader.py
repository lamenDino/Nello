#!/usr/bin/env python3
"""
Social Media Downloader v4.2 (Render-friendly)
- VIDEO + CAROSELLO FOTO (quando yt-dlp ritorna entries immagine)
- Retry "2 tentativi e poi stop" (il bot resta in silenzio se fallisce)
- URL cleaning (TikTok short + Facebook share)
- Return standard per bot Telegram:
  - {"success": True, "type": "video", "file_path": "...", "title": "...", ...}
  - {"success": True, "type": "carousel", "files": ["...","..."], "title": "...", ...}
"""

import os
import asyncio
import logging
import tempfile
from typing import Dict, Optional, List, Tuple

import yt_dlp
import requests

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

        # Cookies (opzionali). Consiglio: NON committarli su GitHub.
        self.instagram_cookies = os.path.join(os.path.dirname(__file__), "cookies.txt")
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), "youtube_cookies.txt")

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1",
        ]

        # yt-dlp base options
        self.base_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(self.temp_dir, "%(title)s_%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "max_filesize": 50 * 1024 * 1024,  # 50MB (limite pratico Telegram bot)
        }

        # Richiesta tua: prova 2 volte e poi silenzio
        self.max_retries = 2
        self.retry_delay = 2

    # --------------------------
    # Helpers
    # --------------------------

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

    def clean_url(self, url: str) -> str:
        url = (url or "").strip()

        # Facebook /share/ & simili: risolvi redirect
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

        # TikTok short URLs
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

        # Rimuovi querystring
        if "?" in url:
            url = url.split("?", 1)[0]

        return url

    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        opts = self.base_opts.copy()

        opts["http_headers"] = {
            "User-Agent": self.get_random_user_agent(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # Instagram cookies
        if "instagram" in url.lower() and os.path.exists(self.instagram_cookies):
            opts["cookiefile"] = self.instagram_cookies

        # YouTube (shorts etc.)
        if "youtube" in url.lower() or "youtu.be" in url.lower():
            # Se vuoi limitare agli shorts: match_filters con durata <= 60
            # opts["match_filters"] = ["duration<=60"]

            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts["cookiefile"] = self.youtube_cookies

            opts["http_headers"].update(
                {
                    "Referer": "https://www.youtube.com/",
                    "Origin": "https://www.youtube.com",
                }
            )

        # Facebook
        if "facebook" in url.lower():
            opts["http_headers"].update(
                {
                    "Referer": "https://www.facebook.com/",
                    "Origin": "https://www.facebook.com",
                }
            )

        # TikTok
        if "tiktok" in url.lower():
            opts["http_headers"].update(
                {
                    "Referer": "https://www.tiktok.com/",
                    "Origin": "https://www.tiktok.com",
                }
            )

        return opts

    # --------------------------
    # Core: extract + download
    # --------------------------

    async def extract_info(self, url: str, attempt: int = 0) -> Optional[Dict]:
        try:
            opts = self.get_ydl_opts(url, attempt)
            opts["skip_download"] = True

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            return await loop.run_in_executor(None, _extract)

        except Exception as e:
            logger.error(f"Extract info attempt {attempt}: {str(e)[:200]}")
            return None

    def _is_playlist_like(self, info: Dict) -> bool:
        return isinstance(info, dict) and isinstance(info.get("entries"), list) and len(info.get("entries")) > 0

    def _pick_best_image_url(self, entry: Dict) -> Optional[Tuple[str, str]]:
        """
        Ritorna (url, ext) migliore per una singola slide immagine.
        Prova entry['url'] oppure i formats.
        """
        u = entry.get("url")
        ext = (entry.get("ext") or "").lower()
        if u and ext in ("jpg", "jpeg", "png", "webp"):
            return u, ("jpg" if ext == "jpeg" else ext)

        formats = entry.get("formats") or []
        candidates = []
        for f in formats:
            fu = f.get("url")
            fext = (f.get("ext") or "").lower()
            if fu and fext in ("jpg", "jpeg", "png", "webp"):
                score = (f.get("width") or 0) * (f.get("height") or 0)
                score = score if score > 0 else (f.get("filesize") or 0)
                candidates.append((score, fu, ("jpg" if fext == "jpeg" else fext)))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, fu, fext = candidates[0]
            return fu, fext

        return None

    async def _download_carousel_images(self, info: Dict) -> List[str]:
        """
        Scarica immagini da info['entries'] (carosello) e ritorna i file paths.
        """
        files: List[str] = []
        entries = info.get("entries") or []
        headers = {"User-Agent": self.get_random_user_agent()}

        for idx, entry in enumerate(entries, start=1):
            best = self._pick_best_image_url(entry)
            if not best:
                continue

            img_url, ext = best
            safe_id = entry.get("id") or f"{idx}"
            filename = os.path.join(self.temp_dir, f"carousel_{safe_id}_{idx}.{ext}")

            try:
                r = requests.get(img_url, headers=headers, stream=True, timeout=20)
                r.raise_for_status()
                with open(filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)

                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    files.append(filename)
            except Exception as e:
                logger.warning(f"Carousel img download failed idx={idx}: {str(e)[:120]}")
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass

        return files

    async def download_with_ytdlp(self, url: str, attempt: int = 0) -> Optional[str]:
        """
        Download video singolo (non carosello) con yt-dlp
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

            # Estensioni alternative
            if filename:
                base = os.path.splitext(filename)[0]
                for ext in [".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv"]:
                    test_file = base + ext
                    if os.path.exists(test_file):
                        return test_file

            return None

        except Exception as e:
            logger.error(f"Download attempt {attempt}: {str(e)[:200]}")
            return None

    # --------------------------
    # Public API
    # --------------------------

    async def download_video(self, url: str) -> Dict:
        """
        Entry point:
        - 2 tentativi
        - se carosello -> scarica immagini e ritorna type=carousel
        - altrimenti -> scarica video e ritorna type=video
        """
        clean_url = self.clean_url(url)
        platform = self.detect_platform(clean_url)

        for attempt in range(self.max_retries):
            try:
                info = await self.extract_info(clean_url, attempt)

                if not info:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return {"success": False, "error": "extraction_failed"}

                title = info.get("title") or "N/A"
                uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Sconosciuto"

                # Se è un carosello (entries)
                if self._is_playlist_like(info):
                    files = await self._download_carousel_images(info)
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

                    # entries ma non siamo riusciti a scaricare immagini -> fallback video
                    # (alcune piattaforme danno entries che non sono immagini)
                    # Continuiamo col flusso video sotto.

                # Download video
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

                # Se fallisce, ritenta (max 2)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue

                return {"success": False, "error": "download_failed"}

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)[:200]}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return {"success": False, "error": "exception"}
