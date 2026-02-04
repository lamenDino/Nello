#!/usr/bin/env python3
"""
Social Media Downloader v4.2
- VIDEO + CAROSELLO FOTO (Instagram/TikTok/Facebook/etc.)
- Retry robusto
- URL cleaning (TikTok short + Facebook share)
- Return standardizzato per bot Telegram:
  - {"success": True, "type": "video", "file_path": "...", ...}
  - {"success": True, "type": "carousel", "files": ["...","..."], ...}
"""

import os
import asyncio
import logging
import tempfile
from typing import Dict, Optional, List, Tuple

import yt_dlp
import requests
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    def __init__(self, debug: bool = False):
        self.temp_dir = tempfile.gettempdir()

        # Percorsi cookies (opzionali)
        self.instagram_cookies = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')

        # User-Agent pool
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1',
        ]

        # Base options yt-dlp
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'max_filesize': 50 * 1024 * 1024,
        }

        self.max_retries = 3
        self.retry_delay = 2
        self.debug = bool(debug)
        self._last_info = None
        if self.debug:
            self.debug_dir = os.path.join(self.temp_dir, 'smd_debug')
            try:
                os.makedirs(self.debug_dir, exist_ok=True)
            except Exception:
                pass

    def _save_debug_info(self, note: str = '') -> Optional[str]:
        if not self.debug or not self._last_info:
            return None
        try:
            ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            safe_note = ''.join([c for c in note if c.isalnum() or c in ('_', '-')])[:40]
            fname = f"info_{ts}_{safe_note}.json" if safe_note else f"info_{ts}.json"
            path = os.path.join(self.debug_dir, fname)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(self._last_info, fh, default=str, indent=2, ensure_ascii=False)
            logger.info(f"Saved debug info to {path}")
            return path
        except Exception as e:
            logger.warning(f"Failed saving debug info: {e}")
            return None

    # --------------------------
    # Helpers
    # --------------------------

    def get_random_user_agent(self) -> str:
        import random
        return random.choice(self.user_agents)

    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        """Opzioni yt-dlp personalizzate per piattaforma"""
        opts = self.base_opts.copy()

        opts['http_headers'] = {
            'User-Agent': self.get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        # Instagram cookies
        if 'instagram' in url.lower() and os.path.exists(self.instagram_cookies):
            opts['cookiefile'] = self.instagram_cookies

        # YouTube: cookies + headers
        if 'youtube' in url.lower() or 'youtu.be' in url.lower():
            # Shorts spesso <= 60
            opts['match_filters'] = ['duration<=60']
            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts['cookiefile'] = self.youtube_cookies
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })

        # Facebook headers
        if 'facebook' in url.lower() or 'fb.' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.facebook.com/',
                'Origin': 'https://www.facebook.com',
            })

        # TikTok headers
        if 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })

        return opts

    def clean_url(self, url: str) -> str:
        """Pulisce URL e risolve short link (TikTok / Facebook share)"""
        url = url.strip()

        # Facebook /share/
        if 'facebook.com/share/' in url:
            try:
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={'User-Agent': self.get_random_user_agent()}
                )
                url = response.url
            except Exception:
                pass

        # TikTok short URLs
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={'User-Agent': self.get_random_user_agent()}
                )
                url = response.url
            except Exception:
                pass

        # Rimuovi parametri
        if '?' in url:
            url = url.split('?')[0]

        return url

    def detect_platform(self, url: str) -> str:
        """Rileva piattaforma"""
        u = url.lower()
        if 'tiktok' in u:
            return 'tiktok'
        if 'instagram' in u or 'ig.tv' in u:
            return 'instagram'
        if 'facebook' in u or 'fb.' in u:
            return 'facebook'
        if 'youtube' in u or 'youtu.be' in u:
            return 'youtube'
        if 'twitter' in u or 'x.com' in u:
            return 'twitter'
        return 'unknown'

    def get_error_message_for_platform(self, platform: str, error_type: str) -> str:
        messages = {
            'youtube': {
                'extraction_failed': '🤖 YouTube chiede autenticazione. Riprova tra poco.',
                'download_failed': '⚠️ Non riesco a scaricare lo short. Riprova.',
            },
            'facebook': {
                'extraction_failed': '⚠️ Facebook ha cambiato struttura. Riprova con un altro reel.',
                'download_failed': '🔒 Non riesco a scaricare il reel. Potrebbe essere privato.',
            },
            'instagram': {
                'extraction_failed': '🔒 Post privato o cookies scaduti.',
                'download_failed': '📸 Non riesco a scaricare il contenuto Instagram.',
            },
            'tiktok': {
                'extraction_failed': '⚠️ Errore nel caricamento da TikTok.',
                'download_failed': '🔒 Contenuto TikTok non disponibile.',
            },
        }
        return messages.get(platform, {}).get(error_type, '❌ Errore nel download.')

    # --------------------------
    # Core: extract + download
    # --------------------------

    async def extract_info(self, url: str, attempt: int = 0) -> Optional[Dict]:
        """Estrae info (senza download)"""
        try:
            opts = self.get_ydl_opts(url, attempt)
            opts['skip_download'] = True

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            return await loop.run_in_executor(None, _extract)

        except Exception as e:
            logger.error(f"Extract info attempt {attempt}: {str(e)[:200]}")
            return None

    def _pick_best_image_url(self, entry: Dict) -> Optional[Tuple[str, str]]:
        """
        Ritorna (url, ext) migliore per una singola slide immagine.
        Prova entry['url'] oppure i formats.
        """
        # Caso semplice
        u = entry.get('url')
        ext = (entry.get('ext') or '').lower()
        if u and ext in ('jpg', 'jpeg', 'png', 'webp'):
            return u, ('jpg' if ext == 'jpeg' else ext)

        # Prova formats
        formats = entry.get('formats') or []
        candidates = []
        for f in formats:
            fu = f.get('url')
            fext = (f.get('ext') or '').lower()
            if fu and fext in ('jpg', 'jpeg', 'png', 'webp'):
                score = (f.get('width') or 0) * (f.get('height') or 0)
                score = score if score > 0 else (f.get('filesize') or 0)
                candidates.append((score, fu, ('jpg' if fext == 'jpeg' else fext)))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, fu, fext = candidates[0]
            return fu, fext

        # Supporto campi immagine tipici di Instagram
        # display_url, original_url, thumbnail, image_url
        img_fields = [
            ('display_url', 'jpg'),
            ('original_url', 'jpg'),
            ('thumbnail', 'jpg'),
            ('thumbnail_url', 'jpg'),
            ('image_url', 'jpg'),
        ]
        for key, guessed_ext in img_fields:
            v = entry.get(key)
            if v and isinstance(v, str) and v.startswith('http'):
                return v, guessed_ext

        # Alcuni extractor (instagram) forniscono display_resources o image_versions2
        dr = entry.get('display_resources') or []
        if dr and isinstance(dr, list):
            candidates = []
            for r in dr:
                src = r.get('src') or r.get('url')
                width = r.get('config_width') or r.get('width') or 0
                if src and isinstance(src, str):
                    candidates.append((width or 0, src))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1], 'jpg'

        iv2 = entry.get('image_versions2') or {}
        cand = iv2.get('candidates') or []
        if cand and isinstance(cand, list):
            candidates = []
            for c in cand:
                src = c.get('url')
                width = c.get('width') or 0
                if src:
                    candidates.append((width, src))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1], 'jpg'

        return None

    def _is_playlist_like(self, info: Dict) -> bool:
        return isinstance(info, dict) and isinstance(info.get('entries'), list) and len(info.get('entries')) > 0

    def _pick_best_video_url(self, entry: Dict) -> Optional[Tuple[str, str]]:
        """
        Ritorna (url, ext) migliore per una singola slide video.
        Prova entry['url'] oppure i formats. Restituisce None se non trova video.
        """
        video_exts = ('mp4', 'm4v', 'mov', 'webm', 'mkv', 'ts', '3gp')

        # Caso semplice: entry['url'] con estensione video
        u = entry.get('url')
        ext = (entry.get('ext') or '').lower()
        if u and ext in video_exts:
            return u, ext

        # Cerca nei formats
        formats = entry.get('formats') or []
        candidates = []
        for f in formats:
            fu = f.get('url')
            fext = (f.get('ext') or '').lower()
            if fu and fext in video_exts:
                score = (f.get('width') or 0) * (f.get('height') or 0)
                score = score if score > 0 else (f.get('filesize') or 0)
                candidates.append((score, fu, ('mp4' if fext == 'm4v' else fext)))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, fu, fext = candidates[0]
            return fu, fext

        # Fallback: alcuni extractor mettono video_url o video
        for key in ('video_url', 'video', 'video_src'):
            v = entry.get(key)
            if v and isinstance(v, str) and v.startswith('http'):
                guessed = os.path.splitext(v.split('?')[0])[1].lstrip('.') or 'mp4'
                guessed = guessed if guessed in video_exts else 'mp4'
                return v, guessed

        return None

    async def _download_carousel_items(self, info: Dict) -> List[str]:
        """
        Scarica immagini e video da info['entries'] (carosello) e ritorna file paths.
        Gestisce slide che possono essere immagini o video.
        """
        files: List[str] = []
        entries = info.get('entries') or []
        headers = {'User-Agent': self.get_random_user_agent()}

        for idx, entry in enumerate(entries, start=1):
            safe_id = entry.get('id') or f"{idx}"

            # Determina se la slide è video
            is_video = bool(entry.get('is_video'))
            # Alcuni extractor non impostano is_video ma hanno formats video
            if not is_video:
                fmts = entry.get('formats') or []
                for f in fmts:
                    fext = (f.get('ext') or '').lower()
                    if fext in ('mp4', 'webm', 'mov', 'mkv'):
                        is_video = True
                        break

            if is_video:
                best = self._pick_best_video_url(entry)
                if not best:
                    logger.warning(f"Nessun url video trovato per slide idx={idx}")
                    continue

                video_url, ext = best
                filename = os.path.join(self.temp_dir, f"carousel_{safe_id}_{idx}.{ext}")

                try:
                    r = requests.get(video_url, headers=headers, stream=True, timeout=60)
                    r.raise_for_status()
                    with open(filename, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)

                    if os.path.exists(filename) and os.path.getsize(filename) > 0:
                        files.append(filename)
                    else:
                        try:
                            if os.path.exists(filename):
                                os.remove(filename)
                        except Exception:
                            pass

                except Exception as e:
                    logger.warning(f"Carousel video download failed idx={idx}: {str(e)[:120]}")
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass

            else:
                # Tratta come immagine
                best = self._pick_best_image_url(entry)
                if not best:
                    continue

                img_url, ext = best
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
        """Download singolo (video) con yt-dlp"""
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

            # Fallback estensioni
            if filename:
                base = os.path.splitext(filename)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv']:
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
        Main download.
        Ritorna:
        - success False => {success: False, error: "..."}
        - success True & video => {success: True, type:'video', file_path:'...', title/uploader/platform/url}
        - success True & carousel => {success: True, type:'carousel', files:[...], title/uploader/platform/url}
        """
        clean_url = self.clean_url(url)
        platform = self.detect_platform(clean_url)

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Tentativo {attempt + 1}/{self.max_retries} per {platform}: {clean_url}")

                info = await self.extract_info(clean_url, attempt)
                # conserva l'ultimo info estratto per debug
                self._last_info = info
                if not info:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return {'success': False, 'error': self.get_error_message_for_platform(platform, 'extraction_failed')}

                # Uploader/title (fallbacks)
                uploader = info.get('uploader') or info.get('channel') or info.get('creator') or 'Sconosciuto'
                title = info.get('title') or 'Contenuto'

                # 1) Se è carosello/playlist -> prova a scaricare immagini/video
                if self._is_playlist_like(info):
                    items = await self._download_carousel_items(info)
                    if items:
                        return {
                            'success': True,
                            'type': 'carousel',
                            'files': items,
                            'title': title,
                            'uploader': uploader,
                            'platform': platform,
                            'url': clean_url
                        }
                    # Se non riesce a scaricare immagini/video, prova comunque come video
                    logger.info("Carosello rilevato ma nessuna immagine/video scaricata. Provo come video...")
                    if self.debug:
                        self._save_debug_info('carousel_no_items')

                # 2) Prova come video singolo
                file_path = await self.download_with_ytdlp(clean_url, attempt)
                if not file_path or not os.path.exists(file_path):
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return {'success': False, 'error': self.get_error_message_for_platform(platform, 'download_failed')}

                return {
                    'success': True,
                    'type': 'video',
                    'file_path': file_path,
                    'title': title,
                    'uploader': uploader,
                    'duration': info.get('duration', 0),
                    'platform': platform,
                    'url': clean_url
                }

            except Exception as e:
                err = str(e).lower()
                logger.error(f"Tentativo {attempt + 1} fallito: {str(e)[:200]}")

                # Errori specifici
                if 'sign in' in err or 'bot' in err:
                    return {'success': False, 'error': '🤖 YouTube chiede autenticazione (bot detection). Riprova tra poco.'}
                if 'cannot parse' in err or 'parse' in err:
                    return {'success': False, 'error': '⚠️ Facebook ha cambiato struttura. Riprova con un altro reel.'}
                if 'no video formats found' in err:
                    return {'success': False, 'error': '🔒 Contenuto privato o inaccessibile.'}

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        return {'success': False, 'error': 'Download fallito dopo multiple tentativi. Riprova più tardi.'}
