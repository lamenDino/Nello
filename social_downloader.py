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
import time
from typing import Dict, Optional, List, Tuple
import http.cookiejar

import yt_dlp
import requests
import json
import re
import html
from datetime import datetime

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    def __init__(self, debug: bool = False):
        self.temp_dir = tempfile.gettempdir()

        # Funzione helper per risolvere i path dei cookie (Supporto Render Secret Files & Env Vars)
        def resolve_cookie_path(filename, env_var_names=None):
            # 1. Cerca nelle variabili d'ambiente (PRIORITÀ ALTA per Render)
            if env_var_names:
                if isinstance(env_var_names, str):
                    env_var_names = [env_var_names]
                
                for env_var in env_var_names:
                    content = os.getenv(env_var)
                    if content and len(content.strip()) > 10: # Check minimo validità
                        try:
                            # Crea un file temporaneo con il contenuto
                            temp_cookie_path = os.path.join(self.temp_dir, f"env_{filename}")
                            with open(temp_cookie_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            logger.info(f"Cookie creato da variabile d'ambiente {env_var}: {temp_cookie_path}")
                            return temp_cookie_path
                        except Exception as e:
                            logger.error(f"Errore scrittura cookie da env {env_var}: {e}")

            # 2. Cerca in /etc/secrets/ (standard Render Secret Files)
            found_secret_path = None
            
            # 2a. Cerca con il filename originale (es. cookies.txt)
            path_orig = os.path.join('/etc/secrets', filename)
            if os.path.exists(path_orig):
                found_secret_path = path_orig

            # 2b. Cerca con i nomi delle variabili (es. INSTAGRAM_COOKIES) se non trovato prima
            if not found_secret_path and env_var_names:
                if isinstance(env_var_names, str):
                    check_names = [env_var_names]
                else:
                    check_names = env_var_names
                
                for name in check_names:
                    path_alias = os.path.join('/etc/secrets', name)
                    if os.path.exists(path_alias):
                        found_secret_path = path_alias
                        break
            
            # Se abbiamo trovato un secret, lo copiamo in TEMP perché /etc/secrets è Read-Only
            if found_secret_path:
                try:
                    logger.info(f"Cookie trovato in secrets: {found_secret_path}")
                    # Creiamo un nome file sicuro per la temp dir
                    safe_name = f"copy_{os.path.basename(found_secret_path)}_{filename}"
                    temp_copy_path = os.path.join(self.temp_dir, safe_name)
                    
                    # Copia contenuto
                    with open(found_secret_path, 'rb') as f_src:
                        content = f_src.read()
                    with open(temp_copy_path, 'wb') as f_dst:
                        f_dst.write(content)
                        
                    logger.info(f"Copiato cookie secret in scrivibile: {temp_copy_path}")
                    return temp_copy_path
                except Exception as e:
                    logger.error(f"Errore durante la copia del secret file {found_secret_path}: {e}")
                    # Se fallisce la copia, ritorniamo l'originale sperando che yt-dlp non debba scriverci
                    return found_secret_path

            # 3. Cerca nella directory corrente (Fallback locale / git)
            local_path = os.path.join(os.path.dirname(__file__), filename)
            # Se esiste torniamo questo, ma logghiamo che è un fallback
            if os.path.exists(local_path):
                logger.info(f"Uso cookie locale (fallback): {local_path}")
                return local_path
            
            logger.warning(f"Cookie {filename} non trovato da nessuna parte.")
            return local_path # Ritorna il percorso locale come default per evitare crash immediati su path null

        # Percorsi cookies
        self.instagram_cookies = resolve_cookie_path('cookies.txt', ['INSTAGRAM_COOKIES', 'COOKIES_TXT'])
        self.youtube_cookies = resolve_cookie_path('youtube_cookies.txt', 'YOUTUBE_COOKIES')
        self.tiktok_cookies = resolve_cookie_path('tiktok_cookies.txt', 'TIKTOK_COOKIES')
        self.facebook_cookies = resolve_cookie_path('facebook_cookies.txt', 'FACEBOOK_COOKIES')

        # Proxy opzionale (es. http://user:pass@host:port)
        self.proxy = (
            os.getenv('SMD_PROXY')
            or os.getenv('HTTPS_PROXY')
            or os.getenv('HTTP_PROXY')
        )
        self.proxy = self.proxy.strip() if self.proxy else None
        self.proxy_dict = {'http': self.proxy, 'https': self.proxy} if self.proxy else None
        
        # State per i fallback
        self.last_fallback_title = None

        # User-Agent pool
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]

        # Base options yt-dlp
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title).150s_%(id)s.%(ext)s'),
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

    def _load_netscape_cookies(self, path: str) -> Optional[Dict[str, str]]:
        if not path or not os.path.exists(path):
            return None
        cookies: Dict[str, str] = {}
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        name = parts[5]
                        value = parts[6]
                        cookies[name] = value
        except Exception:
            return None
        return cookies or None

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

        if self.proxy:
            opts['proxy'] = self.proxy

        # --- STRATEGIA DI DOWNLOAD (Priorità No-Cookies su Render) ---
        # Attempt 0: NO Cookies (prova accesso pubblico/mobile client)
        # Attempt 1: SI Cookies (se disponibili, fallback authenticated)
        # Attempt 2: NO Cookies (fallback aggressivo / scraping)

        # Instagram
        if 'instagram' in url.lower():
            # Tentativo 0: Senza cookies (spesso funziona meglio su IP server puliti)
            if attempt == 0:
                pass 
            # Tentativo 1: Con cookies (se esistono)
            elif attempt == 1 and os.path.exists(self.instagram_cookies):
                 opts['cookiefile'] = self.instagram_cookies
            # Tentativo 2: Con cookies (ultimo tentativo)
            elif attempt >= 2 and os.path.exists(self.instagram_cookies):
                 opts['cookiefile'] = self.instagram_cookies

        # YouTube: strategie anti-block
        if 'youtube' in url.lower() or 'youtu.be' in url.lower():
            opts['format'] = 'bestvideo+bestaudio/best'
            opts['merge_output_format'] = 'mp4'
            
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })

            # Attempt 0: Android Client (No Cookies) - Molto efficace per Shorts
            if attempt == 0:
                opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
            
            # Attempt 1: iOS Client (No Cookies)
            elif attempt == 1:
                opts['extractor_args'] = {'youtube': {'player_client': ['ios']}}

            # Attempt 2: Web Client Standard + Cookies (se ci sono)
            else:
                if os.path.exists(self.youtube_cookies):
                    opts['cookiefile'] = self.youtube_cookies
                # else: fallback standard web client

        # Facebook
        if 'facebook' in url.lower() or 'fb.' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.facebook.com/',
                'Origin': 'https://www.facebook.com',
            })
            
            # Facebook è difficile. 
            # Attempt 0: No Cookies (Public access)
            # Attempt 1+: Cookies
            if attempt > 0 and os.path.exists(self.facebook_cookies):
                opts['cookiefile'] = self.facebook_cookies

        # TikTok headers
        if 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })
            # Use cookies only on retries or if forced
            if attempt > 0 and os.path.exists(self.tiktok_cookies):
                opts['cookiefile'] = self.tiktok_cookies

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
                    headers={'User-Agent': self.get_random_user_agent()},
                    proxies=self.proxy_dict
                )
                url = response.url
            except Exception:
                pass

        # TikTok short URLs
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                headers = {
                    'User-Agent': self.get_random_user_agent(),
                    'Referer': 'https://www.tiktok.com/',
                    'Origin': 'https://www.tiktok.com'
                }
                cookies = self._load_netscape_cookies(self.tiktok_cookies)

                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers=headers,
                    cookies=cookies,
                    proxies=self.proxy_dict
                )
                if response.url and '/login' not in response.url:
                    url = response.url
                else:
                    # Fallback GET se HEAD porta a /login
                    response = requests.get(
                        url,
                        allow_redirects=True,
                        timeout=15,
                        headers=headers,
                        cookies=cookies,
                        proxies=self.proxy_dict
                    )
                    if response.url:
                        url = response.url
            except Exception:
                pass

        # Smart clean parameters (strip tracking, keep functional)
        if '?' in url:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # List of params to remove
            tracking_params = [
                'fbclid', 'igsh', 'si', 'utm_source', 'utm_medium', 
                'utm_campaign', 'utm_term', 'utm_content', 'share_id',
                'mode', 'u_code', 'timestamp', 'user_id', 'sec_user_id',
                'utm_id', 'gclid', '_ga'
            ]
            
            # Keep only safe params
            new_params = {}
            for k, v in params.items():
                if k.lower() not in tracking_params:
                    new_params[k] = v
                    
            # Reconstruct
            new_query = urlencode(new_params, doseq=True)
            url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))

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
        # Nota: rimuoviamo il try/catch interno per permettere a download_video
        # di intercettare errori specifici (es. Unsupported URL)
        opts = self.get_ydl_opts(url, attempt)
        opts['skip_download'] = True

        loop = asyncio.get_event_loop()

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        return await loop.run_in_executor(None, _extract)

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
                    r = requests.get(
                        video_url,
                        headers=headers,
                        stream=True,
                        timeout=60,
                        proxies=self.proxy_dict
                    )
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
                    r = requests.get(
                        img_url,
                        headers=headers,
                        stream=True,
                        timeout=20,
                        proxies=self.proxy_dict
                    )
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

    async def _facebook_fallback(self, url: str) -> Optional[List[str]]:
        """Fallback for Facebook posts (images) using requests + regex"""
        try:
            headers = {
                'User-Agent': self.get_random_user_agent(),
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://www.facebook.com/',
                'Origin': 'https://www.facebook.com',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Upgrade-Insecure-Requests': '1',
            }
            # Load cookies if available
            cookies = self._load_netscape_cookies(self.facebook_cookies) if hasattr(self, 'facebook_cookies') else None

            loop = asyncio.get_event_loop()
            
            def _fetch():
                return requests.get(url, headers=headers, cookies=cookies, timeout=15)
            
            resp = await loop.run_in_executor(None, _fetch)
            if resp.status_code != 200:
                logger.warning(f"Facebook fallback: status code {resp.status_code} for {url}")
                return None
                
            text = resp.text

            # --- DETECT VIDEO ---
            # Se il link è esplicitamente un video (controllato dalla presenza di video indicators nel meta), 
            # e siamo qui (fallback immagini), significa che yt-dlp ha fallito. 
            # L'utente non vuole la foto se è un video.
            video_indicators = [
                r'<meta\s+property="og:type"\s+content="video',
                r'<meta\s+property="og:video"',
                r'<meta\s+name="twitter:player"',
                r'"__typename":"Video"',
                r'"is_video":true'
            ]
            is_video_page = False
            for vi in video_indicators:
                if re.search(vi, text, re.IGNORECASE):
                    is_video_page = True
                    break
            
            # Se sembra un video, controlla se l'URL non era esplicitamente una foto
            if is_video_page and '/photo' not in url:
                # Tenta un ultimo fallback brutale: cerca .mp4 nel sorgente
                # A volte fb restituisce il link .mp4 in chiaro anche se yt-dlp non riesce a parsare
                logger.info("Facebook fallback: detected VIDEO page. Searching for raw .mp4 link...")
                mp4_matches = re.findall(r'"(https?:\/\/[^"]+\.mp4[^"]*)"', text.replace(r'\/', '/'))
                if mp4_matches:
                    best_mp4 = mp4_matches[0]
                    # Filtra mp4
                    for m in mp4_matches:
                         if 'sd_src' in m or 'hd_src' in m:
                            best_mp4 = m
                            break
                    
                    logger.info(f"Facebook fallback: FOUND raw mp4. Downloading...")
                    mp4_url = html.unescape(best_mp4)
                    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                    tmp_mp4 = os.path.join(self.temp_dir, f"fb_{ts}_fallback.mp4")
                    
                    def _dl_mp4():
                        try:
                            r = requests.get(mp4_url, headers=headers, stream=True, timeout=60)
                            if r.status_code == 200:
                                with open(tmp_mp4, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=1024*1024):
                                        if chunk:
                                            f.write(chunk)
                                return True
                        except Exception:
                            return False
                        return False
                    
                    try:
                        mp4_success = await loop.run_in_executor(None, _dl_mp4)
                        if mp4_success and os.path.exists(tmp_mp4) and os.path.getsize(tmp_mp4) > 1000:
                             return [tmp_mp4]
                    except Exception as e:
                        logger.warning(f"Facebook fallback MP4 download failed: {e}")
                    # Let's abort image fallback for video.
                logger.info("Facebook fallback: detected VIDEO content and no raw mp4 found. Aborting.")
                return None
            
            # Regex for og:image - try multiple patterns
            # Spesso l'ordine degli attributi cambia o ci sono spazi diversi
            img_url = None
            patterns = [
                r'<meta\s+property="og:image"\s+content="([^"]+)"',
                r'<meta\s+content="([^"]+)"\s+property="og:image"',
                r'<meta\s+name="og:image"\s+content="([^"]+)"',
                r'<meta\s+name="twitter:image"\s+content="([^"]+)"',
                r'"image":\s*"([^"]+)"',
                r'"contentUrl":\s*"([^"]+)"'
            ]
            
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    candidate = html.unescape(m.group(1))
                    candidate_lower = candidate.lower()
                    # Ignore common "ghost" or "placeholder" images
                    if 'profile_pic' in candidate_lower or 'static.xx' in candidate_lower or 'blank.jpg' in candidate_lower:
                        continue
                    if 's40x40' in candidate_lower or 's50x50' in candidate_lower: # Low res thumbnails
                        continue
                    if 'generic' in candidate_lower or 'ad_image' in candidate_lower:
                        continue
                    # Filtra immagini grigie di default
                    if 'gray_profile' in candidate_lower or 'silhouette' in candidate_lower:
                        continue
                        
                    img_url = candidate
                    break

            # Handle /share/ redirects if requests didn't follow them completely (JS redirects)
            if not img_url and 'share/' in url:
                # Try to find the canonical URL in the HTML
                # <link rel="canonical" href="...">
                can_pat = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', text)
                if can_pat:
                    real_url = html.unescape(can_pat.group(1))
                    if real_url != url:
                        logger.info(f"Facebook fallback: found canonical url {real_url}")
                        # Recursive call with canonical URL might help if it's different
                        # But be careful of infinite loops. Just try to use it for next steps or return self._facebook_fallback(real_url)
                        pass
            
            # Se ancora nullo, cerca URL diretti di immagini fbcdn ad alta qualità
            if not img_url:
                # Cerca URL che iniziano con http/https e finiscono con .jpg (anche con parametri dopo)
                # Esclude escape json per ora, li gestiamo dopo
                raw_matches = re.findall(r'(https?:\/\/[^"\s]+\.jpg[^"\s]*)', text.replace(r'\/', '/'))
                for m in raw_matches:
                    u = html.unescape(m)
                    u_lower = u.lower()
                    # Filtri rigorosi per immagini spazzatura
                    bad_terms = [
                         's40x40', 'p50x50', 's80x80', 's200x200', 'width=40', 
                         'static.xx', 'emoji', 'profile_pic', 'blank', 
                         'rsrc.php', 'assets', 'sprite', 'icon',
                         'gray_profile', 'silhouette' # Also here
                    ]
                    if any(bt in u_lower for bt in bad_terms):
                        continue
                    
                    # Se è un link fbcdn valido, prendilo
                    if 'fbcdn.net' in u or 'facebook.com' in u:
                        img_url = u
                        break
                    if 'fbcdn.net' in u:
                        img_url = u
                        break

            if not img_url:
                logger.warning(f"Facebook fallback: no image found in page (len={len(text)})")
                if len(text) < 500:
                    logger.debug(f"Page content: {text}")
                return None

            
            # Download image
            ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            tmp_name = os.path.join(self.temp_dir, f"fb_{ts}_fallback.jpg")
            
            def _dl_img():
                r = requests.get(img_url, headers=headers, timeout=15)
                if r.status_code == 200:
                    with open(tmp_name, 'wb') as f:
                        f.write(r.content)
                    return True
                return False
                
            success = await loop.run_in_executor(None, _dl_img)
            if success:
                # Try to get title too
                t_m = re.search(r'<title>(.*?)</title>', text)
                if t_m:
                    self.last_fallback_title = html.unescape(t_m.group(1))
                return [tmp_name]
            return None
            
        except Exception as e:
            logger.error(f"Facebook fallback error: {e}")
            return None

    async def _tiktok_photo_fallback(self, url: str) -> List[str]:
        """
        Fallback per pagine TikTok /photo/ che yt-dlp non riconosce.
        Scarica la pagina HTML, estrae tutte le immagini (jpg/png/webp) e le salva.
        """
        files: List[str] = []
        found_title = ""
        self.last_fallback_title = None
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.tiktok.com/',
            'Origin': 'https://www.tiktok.com'
        }
        # Force use of ttcokies.txt if available, else tiktok_cookies.txt
        cookie_path = os.path.join(os.path.dirname(__file__), 'ttcokies.txt')
        if not os.path.exists(cookie_path):
             cookie_path = self.tiktok_cookies
        
        cookies = self._load_netscape_cookies(cookie_path)
        if cookies:
             logger.info(f"Loaded {len(cookies)} cookies from {os.path.basename(cookie_path)}")
        else:
             logger.warning(f"No cookies loaded from {os.path.basename(cookie_path)}")

        try:
            logger.info(f"TikTok Fallback: fetching {url}")
            r = requests.get(
                url,
                headers=headers,
                timeout=15,
                cookies=cookies,
                proxies=self.proxy_dict
            )
            logger.info(f"TikTok Fallback: status {r.status_code}, len {len(r.text)}")
            r.raise_for_status()
            html = r.text
            
            with open("tiktok_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            logger.warning(f"Failed fetching TikTok page for fallback: {e}")
            return files

        # Estrai url immagine con regex
        uniq = self._extract_tiktok_photo_urls_from_html(html)
        logger.info(f"TikTok Fallback: found {len(uniq)} images from HTML")

        # Tenta estrazione titolo da HTML (semplice)
        try:
            # es: <title>Video description | TikTok</title>
            match_title = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if match_title:
                t = match_title.group(1)
                t = t.replace('| TikTok', '').strip()
                found_title = t
                self.last_fallback_title = t
        except:
            pass

        if not uniq:
             logger.info("TikTok Fallback: HTML extraction failed, trying TIKWM API...")
             try:
                 api_url = "https://www.tikwm.com/api/"
                 # INCREASED COUNT TO 35 to fix split albums
                 r = requests.post(api_url, data={'url': url, 'count': 35, 'cursor': 0, 'web': 1, 'hd': 1}, timeout=15, proxies=self.proxy_dict)
                 if r.status_code == 200:
                     data = r.json()
                     if data.get('code') == 0:
                         data_obj = data.get('data', {})
                         images = data_obj.get('images', [])
                         logger.info(f"TikTok Fallback: TIKWM API found {len(images)} images")
                         uniq = images
                         
                         # Estrai titolo da API se presente
                         if 'title' in data_obj:
                             found_title = data_obj['title']
                             self.last_fallback_title = found_title
             except Exception as e:
                 logger.warning(f"TikTok Fallback: TIKWM API failed: {e}")

        # Limita numero di immagini
        MAX = 35
        uniq = uniq[:MAX]

        for idx, img_url in enumerate(uniq, start=1):
            ext = os.path.splitext(img_url.split('?')[0])[1].lstrip('.').lower() or 'jpg'
            if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                ext = 'jpg'

            filename = os.path.join(self.temp_dir, f"tiktok_photo_{idx}.{ext}")
            try:
                rr = requests.get(
                    img_url,
                    headers=headers,
                    stream=True,
                    timeout=20,
                    cookies=cookies,
                    proxies=self.proxy_dict
                )
                rr.raise_for_status()
                with open(filename, 'wb') as fh:
                    for chunk in rr.iter_content(1024 * 256):
                        if chunk:
                            fh.write(chunk)
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    files.append(filename)
                else:
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed download fallback image {img_url}: {e}")
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass

        return files

    def _extract_tiktok_photo_urls_from_html(self, html: str) -> List[str]:
        import re

        def _dedupe(items: List[str]) -> List[str]:
            out = []
            for x in items:
                if x not in out:
                    out.append(x)
            return out

        urls: List[str] = []

        # 1) Prova SIGI_STATE o UNIVERSAL_DATA
        # Pattern vecchio: window.SIGI_STATE = {...}
        sigi_match = re.search(r'window\.__SIGI_STATE__\s*=\s*(\{.*?\})\s*;\s*</script>', html, re.DOTALL)
        if not sigi_match:
            # Pattern alternativo: "SIGI_STATE": {...}
            sigi_match = re.search(r'\"SIGI_STATE\"\s*:\s*(\{.*?\})\s*,\s*\"AppContext', html, re.DOTALL)
        if not sigi_match:
             # Pattern script tag: <script id="SIGI_STATE">...</script>
             sigi_match = re.search(r'<script[^>]+id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL)

        # Newer TikTok structure: UNIVERSAL_DATA_FOR_REHYDRATION
        # Pattern variabile:
        univ_match = re.search(r'__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*(\{.*?\})\s*;</script>', html, re.DOTALL)
        if not univ_match:
            # Pattern script tag ID (più comune ora):
            # Relaxed regex to handle spacing and ordering of attributes
            univ_match = re.search(r'<script[^>]+id=[\'"]__UNIVERSAL_DATA_FOR_REHYDRATION__[\'"][^>]*>(.*?)</script>', html, re.DOTALL)

        json_data_list = []
        if sigi_match:
            json_data_list.append(sigi_match.group(1))
        if univ_match:
            json_data_list.append(univ_match.group(1))
            
        logger.info(f"TikTok Fallback: extracted {len(json_data_list)} JSON blobs")

        for idx_json, json_str in enumerate(json_data_list):
            try:
                data = json.loads(json_str)
                
                # DEBUG: Dump JSON to file
                try:
                    with open(f"tiktok_json_dump_{idx_json}.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                except:
                    pass

                # Parse robusto recursive per trovare liste di url
                def recursive_find_images(d):
                    if isinstance(d, dict):
                        # Pattern trovati in struttur tiktok
                        if 'imageURL' in d and 'urlList' in d['imageURL']:
                             urls.extend(d['imageURL']['urlList'])
                        if 'displayImage' in d and 'urlList' in d['displayImage']:
                             urls.extend(d['displayImage']['urlList'])
                        
                        for k, v in d.items():
                            recursive_find_images(v)
                    elif isinstance(d, list):
                        for i in d:
                            recursive_find_images(i)
                
                recursive_find_images(data)
                logger.info(f"TikTok Fallback: JSON blob {idx_json} processed, total urls: {len(urls)}")
            except Exception as e:
                logger.warning(f"TikTok Fallback: JSON blob {idx_json} parse error: {e}")
                pass

        # 2) Regex generico immagini
        # Cerca URL che sembrano immagini tiktok
        # Spesso sono https://p16-sign-va.tiktokcdn.com/...o qualcosa del genere
        if not urls:
            logger.info("TikTok Fallback: No JSON data found, trying regex...")
            # Pattern broad per URL immagini dentro stringhe
            pattern = re.compile(r'"(https?://[^"\s]+\.(?:jpeg|jpg|png|webp)[^"]*)"', re.IGNORECASE)
            matches = pattern.findall(html)
            # Filtra per domini tiktok se possibile, o prendi tutto
            for m in matches:
                # Decodifica unicode escape se presente
                m_dec = m.encode().decode('unicode_escape')
                if 'tiktokcdn' in m_dec or 'tiktok' in m_dec:
                    urls.append(m_dec)

        # 3) Meta og:image come ultima risorsa
        if not urls:
            meta_patterns = [
                re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
                re.compile(r'<meta[^>]+name=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
            ]
            for mp in meta_patterns:
                mm = mp.findall(html)
                urls.extend(mm)

        return _dedupe(urls)

    def _from_base62(self, s: str) -> int:
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        result = 0
        for char in s:
            result = result * 64 + alphabet.index(char)
        return result

    def _instagram_api_fallback_sync(self, url: str) -> List[str]:
        """
        Fallback per Instagram usando API interna e cookies.
        Estrae media_id da shortcode e chiama endpoint info.
        Esegue chiamate bloccanti (requests), da eseguire in executor.
        """
        files: List[str] = []
        try:
            # Estrai shortcode
            # es: https://www.instagram.com/p/DTvEEVVCO7I/
            match = re.search(r'instagram\.com/(?:p|reel)/([^/?#&]+)', url)
            if not match:
                logger.warning("Instagram API: shortcode not found")
                return []
            
            shortcode = match.group(1)
            media_id = self._from_base62(shortcode)
            logger.info(f"Instagram API: shortcode={shortcode} -> media_id={media_id}")

            api_url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "X-IG-App-ID": "936619743392459",
                "Referer": url,
            }

            cookies = self._load_netscape_cookies(self.instagram_cookies)
            if not cookies:
                 logger.warning("Instagram API: cookies missing, cannot use API fallback")
                 return []

            r = requests.get(api_url, headers=headers, cookies=cookies, timeout=15, proxies=self.proxy_dict)
            if r.status_code != 200:
                logger.warning(f"Instagram API: failed with status {r.status_code}")
                return []

            data = r.json()
            items = data.get('items', [])
            if not items:
                logger.warning("Instagram API: no items in response")
                return []

            item = items[0]
            
            # Recupera title/caption per self.last_fallback_title se serve
            try:
                caption = item.get('caption', {})
                if caption:
                    text = caption.get('text', '')
                    if text:
                        self.last_fallback_title = text
            except:
                pass

            candidates_urls = []
            
            # Check carousel
            if 'carousel_media' in item:
                logger.info(f"Instagram API: found carousel with {len(item['carousel_media'])} items")
                for media in item['carousel_media']:
                    # Video?
                    if 'video_versions' in media:
                        # pick best video
                        vids = media.get('video_versions', [])
                        if vids:
                            # sort by width/height/type? usually index 0 is best
                            candidates_urls.append((vids[0]['url'], 'mp4', True))
                    else:
                        # Image
                        imgs = media.get('image_versions2', {}).get('candidates', [])
                        if imgs:
                            candidates_urls.append((imgs[0]['url'], 'jpg', False))
            else:
                # Single item - FIX: handle single item directly without checking carousel_media again incorrectly
                # Logica corretta per item singolo
                if 'video_versions' in item:
                    vids = item.get('video_versions', [])
                    if vids:
                        candidates_urls.append((vids[0]['url'], 'mp4', True))
                else:
                    imgs = item.get('image_versions2', {}).get('candidates', [])
                    if imgs:
                        candidates_urls.append((imgs[0]['url'], 'jpg', False))

            # Download items
            for idx, (media_url, ext, is_video) in enumerate(candidates_urls, start=1):
                # Adjust ext if query param hints otherwise (like .heic?stp=dst-jpg)
                if '.heic' in media_url and 'dst-jpg' in media_url:
                    ext = 'jpg'

                filename = os.path.join(self.temp_dir, f"insta_api_{shortcode}_{idx}.{ext}")
                logger.info(f"Instagram API: downloading item {idx} to {filename}")
                
                try:
                    rr = requests.get(media_url, headers=headers, stream=True, timeout=30, proxies=self.proxy_dict)
                    rr.raise_for_status()
                    with open(filename, 'wb') as f:
                        for chunk in rr.iter_content(chunk_size=1024 * 256):
                             if chunk:
                                 f.write(chunk)
                    
                    if os.path.exists(filename) and os.path.getsize(filename) > 0:
                        files.append(filename)
                except Exception as e:
                    logger.warning(f"Instagram API: download failed for {media_url}: {e}")

            return files

        except Exception as e:
            logger.warning(f"Instagram API fallback exception: {e}")
            return files

    async def _instagram_api_fallback(self, url: str) -> List[str]:
        """Wrapper asincrono per _instagram_api_fallback_sync"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._instagram_api_fallback_sync, url)

    async def _instagram_photo_fallback(self, url: str) -> List[str]:
        """
        Fallback per post Instagram (foto/carousel) quando non ci sono formati video.
        Scarica la pagina HTML, estrae immagini e le salva.
        """
        files: List[str] = []
        found_description = ""
        self.last_fallback_title = None
        headers = {
            'User-Agent': self.get_random_user_agent(),
            'Referer': 'https://www.instagram.com/',
            'Origin': 'https://www.instagram.com'
        }
        cookies = self._load_netscape_cookies(self.instagram_cookies)

        try:
            logger.info(f"Instagram Fallback: fetching {url}")
            r = requests.get(
                url,
                headers=headers,
                timeout=15,
                cookies=cookies,
                proxies=self.proxy_dict
            )
            logger.info(f"Instagram Fallback: status {r.status_code}, len {len(r.text)}")
            r.raise_for_status()
            html = r.text
        except Exception as e:
            logger.warning(f"Failed fetching Instagram page for fallback: {e}")
            return files

        uniq = self._extract_instagram_image_urls_from_html(html)
        logger.info(f"Instagram Fallback: found {len(uniq)} images")
        
        # Filtra immagini spazzatura (icone, loghi 150x150, ecc.)
        filtered = []
        # Exclude low res, assets, and generic terms
        exclude_terms = [
             '150x150', '320x320', '480x480', 'p50x50', '200x200',
             'logo', 'icon', 'thumbnail', 'sprite', 'assets', 'transparent',
             'signin', 'signup', 'facebook', 'fb_logo', 'badge',
             'instagram_logo', 'error', 'null', 'empty'
        ]
        
        for u in uniq:
            u_lower = u.lower()
            if any(term in u_lower for term in exclude_terms):
                logger.info(f"Skipping junk image: {u}")
                continue
            
            # Additional heuristic: Instagram content images usually have a hash path or 'p1080x1080' or similar
            # If it's very short or looks like a static asset, skip it.
            if '/static/' in u_lower or 'static.cdninstagram' in u_lower:
                 # Check if it really looks like content (usually has long hash)
                 if len(os.path.basename(u.split('?')[0])) < 20:
                     logger.info(f"Skipping static asset: {u}")
                     continue

            filtered.append(u)
        uniq = filtered
        logger.info(f"Instagram Fallback: filtered to {len(uniq)} images")
        
        # Tenta estrazione caption da HTML (meta tags)
        try:
            # es: <meta property="og:description" content="..." />
            match_desc = re.search(r'<meta\s+property="og:description"\s+content="(.*?)"', html, re.IGNORECASE)
            if match_desc:
                found_description = match_desc.group(1)
            else:
                match_title = re.search(r'<meta\s+property="og:title"\s+content="(.*?)"', html, re.IGNORECASE)
                if match_title:
                   found_description = match_title.group(1)
            
            if found_description:
                self.last_fallback_title = found_description
        except:
             pass

        MAX = 30
        uniq = uniq[:MAX]

        for idx, img_url in enumerate(uniq, start=1):
            ext = os.path.splitext(img_url.split('?')[0])[1].lstrip('.').lower() or 'jpg'
            if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                ext = 'jpg'

            filename = os.path.join(self.temp_dir, f"instagram_photo_{idx}.{ext}")
            try:
                rr = requests.get(
                    img_url,
                    headers=headers,
                    stream=True,
                    timeout=20,
                    cookies=cookies,
                    proxies=self.proxy_dict
                )
                rr.raise_for_status()
                with open(filename, 'wb') as fh:
                    for chunk in rr.iter_content(1024 * 256):
                        if chunk:
                            fh.write(chunk)
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    files.append(filename)
                else:
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed download Instagram fallback image {img_url}: {e}")
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass

        return files

    def _extract_instagram_image_urls_from_html(self, html: str) -> List[str]:
        import re

        def _dedupe(items: List[str]) -> List[str]:
            out = []
            for x in items:
                if x not in out:
                    out.append(x)
            return out

        def _collect_urls(obj, urls_out: List[str]):
            if isinstance(obj, dict):
                for v in obj.values():
                    _collect_urls(v, urls_out)
            elif isinstance(obj, list):
                for v in obj:
                    _collect_urls(v, urls_out)
            elif isinstance(obj, str):
                if ('cdninstagram' in obj or 'fbcdn' in obj) and any(ext in obj for ext in ('.jpg', '.jpeg', '.png', '.webp')):
                    urls_out.append(obj)

        urls: List[str] = []

        # 0) Always extract Meta og:image / twitter:image FIRST (Most reliable for single posts)
        meta_patterns = [
            re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
            re.compile(r'<meta[^>]+name=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
            re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
        ]
        for mp in meta_patterns:
            urls.extend(mp.findall(html))

        # 1) window._sharedData
        shared_match = re.search(r'window\._sharedData\s*=\s*(\{.*?\})\s*;\s*</script>', html, re.DOTALL)
        if shared_match:
            try:
                data = json.loads(shared_match.group(1))
                _collect_urls(data, urls)
            except Exception:
                pass

        # 2) __additionalDataLoaded
        add_match = re.search(r'__additionalDataLoaded\([^,]+,\s*(\{.*?\})\s*\);', html, re.DOTALL)
        if add_match:
            try:
                data = json.loads(add_match.group(1))
                _collect_urls(data, urls)
            except Exception:
                pass

        # 3) Regex generico
        pattern = re.compile(r'https?://[^"\'>\s]+\.(?:jpg|jpeg|png|webp)(?:\?[^"\'>\s]*)?', re.IGNORECASE)
        urls.extend([u for u in pattern.findall(html) if 'cdninstagram' in u or 'fbcdn' in u])

        return _dedupe(urls)

    async def download_with_ytdlp(self, url: str, attempt: int = 0) -> Optional[str]:
        """Download singolo (video) con yt-dlp"""
        try:
            opts = self.get_ydl_opts(url, attempt)
            
            # Nota: Strategie specifiche (es. Android client per Youtube) sono ora gestite
            # direttamente dentro get_ydl_opts in base al numero del tentativo.
            
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

    async def get_random_video_url(self, user_url: str) -> Optional[str]:
        """Recupera un URL video casuale da un profilo (TikTok/Instagram/etc)"""
        import random
        try:
            opts = self.get_ydl_opts(user_url)
            opts.update({
                'extract_flat': True,
                'playlistend': 20, # Fetch latest 20
                'quiet': True,
            })
            
            loop = asyncio.get_event_loop()
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(user_url, download=False)
            
            info = await loop.run_in_executor(None, _extract)
            if not info: 
                return None
            
            entries = info.get('entries')
            if not entries:
                return None
                
            # entries might be a generator or list
            valid_urls = []
            for e in entries:
                if e.get('url'):
                    valid_urls.append(e['url'])
            
            if valid_urls:
                return random.choice(valid_urls)
            return None
        except Exception as e:
            logger.warning(f"Failed getting random video from {user_url}: {e}")
            return None

    # --------------------------
    # Cobalt API Fallback (The "No Cookies" Savior)
    # --------------------------
    
    async def download_with_cobalt(self, url: str) -> Optional[Dict]:
        """
        Usa Cobalt API v10 (https://github.com/imputnet/cobalt) per scaricare media 
        senza usare cookie locali né yt-dlp direttamente sulla macchina.
        Ottimo per YouTube/Insta/TikTok su server bloccati.
        Supporta failover su più istanze pubbliche.
        """
        # Lista di istanze pubbliche (V10 compatible)
        # Nota: api.cobalt.tools richiede Turnstile/Key ora, quindi, usiamo mirror community
        # Aggiornato al 2026/02
        cobalt_instances = [
            "https://cobalt.stream",
            "https://cobalt.kep.io",
            "https://cobalt.7th.ch",
            "https://cobalt.q11.app",
            "https://co.wuk.sh", 
            "https://cobalt.tools", # Tentativo finale (ufficiale)
            # Backup instances (often flaky)
            "https://cobalt.arms.tezcatlipoca.org",
            "https://cobalt.xy24.eu",
            "https://dl.khub.ky",
        ]

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Payload aggiornato per API v10 (camelCase)
        payload = {
            "url": url,
            "videoQuality": "1080",
            "audioFormat": "mp3",
            "filenameStyle": "basic",
            # "youtubeVideoCodec": "h264" # Default h264
        }
        
        logger.info(f"Cobalt fallback triggered for: {url}")
        
        loop = asyncio.get_event_loop()

        for base_url in cobalt_instances:
            api_url = f"{base_url}/" # V10 usa root endpoint
            logger.info(f"Trying Cobalt instance: {api_url}")

            try:
                def _req():
                    # Abbassato timeout a 15s per saltare velocemente se lento
                    try:
                        return requests.post(api_url, json=payload, headers=headers, timeout=15)
                    except requests.exceptions.RequestException:
                        return None
                    
                r = await loop.run_in_executor(None, _req)
                
                if r and r.status_code == 200:
                    data = r.json()
                    
                    # Analisi risposta v10/v7 compatibile
                    # v10: status=tunnel/redirect/picker
                    status = data.get("status")
                    
                    download_url = None
                    
                    if status in ["tunnel", "redirect"]:
                        download_url = data.get("url")
                    elif status == "picker":
                        picker_items = data.get("picker", [])
                        if picker_items:
                            # Cerca video
                            for item in picker_items:
                                if item.get("type") == "video":
                                    download_url = item.get("url")
                                    break
                            # Se non trova video, prende il primo (es. foto)
                            if not download_url:
                                download_url = picker_items[0].get("url")
                    elif "url" in data: # Fallback per vecchie versioni (v7) se qualche istanza è vecchia
                        download_url = data["url"]

                    if download_url:
                        logger.info(f"Cobalt download URL found via {base_url}: {download_url}")
                        
                        # Scarica il file
                        def _dl_file():
                            return requests.get(download_url, stream=True, timeout=60)
                        
                        resp = await loop.run_in_executor(None, _dl_file)
                        
                        if resp.status_code == 200:
                            # Salva su file temp
                            ext = "mp4" # Default
                            # Tentativo di indovinare estensione da Content-Type
                            ctype = resp.headers.get("Content-Type", "")
                            if "image" in ctype:
                                ext = "jpg"
                            elif "audio" in ctype:
                                ext = "mp3"
                                
                            filename = os.path.join(self.temp_dir, f"cobalt_{int(time.time())}.{ext}")
                            
                            with open(filename, 'wb') as f:
                                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                                    if chunk:
                                        f.write(chunk)
                                        
                            if os.path.getsize(filename) > 0:
                                return {
                                    "success": True,
                                    "type": "video" if ext == "mp4" else "image", # Semplificazione, Cobalt ritorna tipicamente video uniti
                                    "file_path": filename,
                                    "title": f"Downloaded via Cobalt ({base_url})",
                                    "files": [filename] if ext != "mp4" else [] # Per compatibilità
                                }
                
                # Se status code != 200 o data parsing fallito, logga e continua
                if r:
                     logger.warning(f"Cobalt instance {base_url} failed with {r.status_code}: {r.text[:200]}")
                else:
                     logger.warning(f"Cobalt instance {base_url} failed (connection error)")

            except Exception as e:
                logger.warning(f"Cobalt instance {base_url} error: {e}")
                continue # Prova la prossima istanza

        logger.error("All Cobalt instances failed.")
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

        # TikTok photo: prova subito fallback (yt-dlp spesso non supporta /photo/)
        if platform == 'tiktok' and '/photo/' in clean_url:
            try:
                files = await self._tiktok_photo_fallback(clean_url)
                if files:
                    return {
                        'success': True,
                        'type': 'carousel',
                        'files': files,
                        'title': 'Contenuto',
                        'uploader': 'Sconosciuto',
                        'platform': platform,
                        'url': clean_url
                    }
            except Exception:
                pass

        force_fallback = False
        title = 'Contenuto'
        uploader = 'Sconosciuto'
        
        # --- PHASE 1: STANDARD YT-DLP ATTEMPTS ---
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
                    # Se finiti tentativi yt-dlp, break e vai ai fallback
                    break 

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
                    break # Vai ai fallback

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
                    logger.warning("Bot detection! Breaking to shortcuts.")
                    break # break to safe fallbacks
                if 'cannot parse' in err or 'parse' in err:
                    break
                if 'does not pass match_filter' in err:
                    return {'success': False, 'error': '⚠️ Questo video è troppo lungo. Scarico solo YouTube Shorts (max 120s).'}
                if 'no video formats found' in err or 'unsupported url' in err:
                    break

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        # --- PHASE 2: EMERGENCY FALLBACKS ---
        logger.info("Entering Emergency Fallback Phase...")

        # 1. COBALT API (The Magic Bullet for No-Cookie environments)
        # Proviamo Cobalt per tutto (YouTube, Instagram, TikTok, Twitter, Facebook)
        # Se yt-dlp ha fallito, Cobalt spesso riesce perché usa i propri IP puliti.
        cobalt_result = await self.download_with_cobalt(clean_url)
        if cobalt_result:
            return cobalt_result

        # 2. Platform-Specific Scrapers (Last Resort)

        if 'facebook' in platform:
             try:
                 fb_files = await self._facebook_fallback(clean_url)
                 if fb_files:
                     return {
                         'success': True,
                         'type': 'carousel',
                         'files': fb_files,
                         'title': title,
                         'uploader': uploader,
                         'platform': platform,
                         'url': clean_url
                     }
             except Exception as e:
                 logger.warning(f"Facebook fallback failed: {e}")

        # Dopo i tentativi normali, prova fallback specifici per piattaforme
        if platform == 'tiktok':
            try:
                # Explicit unpacking check
                fallback_resp = await self._tiktok_photo_fallback(clean_url)
                if isinstance(fallback_resp, tuple) and len(fallback_resp) == 2:
                    res_files, res_title = fallback_resp
                else:
                    res_files = fallback_resp
                    res_title = ""
                
                if res_files:
                    return {
                        'success': True,
                        'type': 'carousel',
                        'files': res_files,
                        'title': getattr(self, 'last_fallback_title', None) or res_title if res_title else title,
                        'uploader': uploader,
                        'platform': platform,
                        'url': clean_url
                    }
            except Exception as e:
                logger.warning(f"TikTok fallback failed: {e}")

        if platform == 'instagram':
            try:
                # 1) Prova fallback API interna (più affidabile per caroselli)
                api_files = await self._instagram_api_fallback(clean_url)
                if api_files:
                    title_to_use = getattr(self, 'last_fallback_title', None) or title
                    return {
                        'success': True,
                        'type': 'carousel',
                        'files': api_files,
                        'title': title_to_use,
                        'uploader': uploader,
                        'platform': platform,
                        'url': clean_url
                    }
                
                # 2) Se API fallisce, prova scraping HTML (vecchio metodo)
                fallback_resp = await self._instagram_photo_fallback(clean_url)
                # Explicit unpacking
                if isinstance(fallback_resp, tuple) and len(fallback_resp) == 2:
                    res_files, res_desc = fallback_resp
                else:
                   res_files = fallback_resp
                   res_desc = ""
                
                # Double check filtering if fallback result contained static assets again
                # (Ideally _instagram_photo_fallback should have done it, but double safety)
                if res_files:
                    safe_files = []
                    for f in res_files:
                        if 'static.cdninstagram' not in f and 'rsrc.php' not in f:
                            safe_files.append(f)
                    
                    if safe_files:
                        return {
                            'success': True,
                            'type': 'carousel',
                            'files': safe_files,
                            'title': res_desc if res_desc else title,
                            'uploader': uploader,
                            'platform': platform,
                            'url': clean_url
                        }
            except Exception as e:
                logger.warning(f"Instagram fallback failed: {e}")


        return {'success': False, 'error': 'Download fallito dopo multiple tentativi. Riprova più tardi.'}
