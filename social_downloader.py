#!/usr/bin/env python3
"""
Social Media Downloader v3.3 - FIXED per python-telegram-bot 20.8
- YouTube Shorts: Contorna bot detection con headers e proxy
- Facebook Reels: Retry con user-agent alternati
- Instagram: Fix completo con cookies
- TikTok: Gestione URL short
- Twitter/X: Supporto video
- Gestione errori robusta per tutte le piattaforme
- RETRY AUTOMATICI: 3 tentativi con backoff esponenziale
"""

import os
import asyncio
import logging
import tempfile
import subprocess
from typing import Dict, Optional
import yt_dlp
import requests

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        
        # Percorsi cookies
        self.instagram_cookies = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')
        
        # Controlla e aggiorna yt-dlp
        self.check_ytdlp_version()
        
        # User-Agent pool per evitare blocchi
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
        ]
        
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            'max_filesize': 50 * 1024 * 1024,
        }
        
        # ===== CONFIGURAZIONE RETRY =====
        self.max_retries = 3          # Massimo 3 tentativi
        self.retry_delay = 2          # Delay iniziale in secondi (2, 4, 8)
        
        logger.info("SocialMediaDownloader inizializzato con max_retries=3")

    def check_ytdlp_version(self):
        """Controlla e aggiorna yt-dlp"""
        try:
            result = subprocess.run(
                ['yt-dlp', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout.strip()
            logger.info(f"yt-dlp versione: {version}")
            
            # Aggiorna yt-dlp
            logger.info("Aggiornamento yt-dlp...")
            subprocess.run(
                ['pip', 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                timeout=60
            )
        except Exception as e:
            logger.warning(f"Errore check yt-dlp: {e}")

    def get_random_user_agent(self) -> str:
        """Ritorna un user-agent random"""
        import random
        return random.choice(self.user_agents)

    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        """Ottiene opzioni yt-dlp personalizzate per piattaforma"""
        opts = self.base_opts.copy()
        
        # User-Agent per evitare blocchi
        opts['http_headers'] = {
            'User-Agent': self.get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # Instagram: aggiungi cookies
        if 'instagram' in url.lower():
            if os.path.exists(self.instagram_cookies):
                opts['cookiefile'] = self.instagram_cookies
                logger.info("Instagram: usando cookies")
        
        # YouTube: aggiungi cookies e contorna bot detection
        if 'youtube' in url.lower() or 'youtu.be' in url.lower():
            opts['match_filters'] = ['duration<=60']
            
            # Prova con cookies YouTube se disponibili
            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts['cookiefile'] = self.youtube_cookies
                logger.info("YouTube: usando cookies")
            
            # Aggiungi header specifici per YouTube Shorts
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })
        
        # Facebook: aggiungi headers specifici
        if 'facebook' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.facebook.com/',
                'Origin': 'https://www.facebook.com',
            })
        
        # TikTok: aggiungi headers
        if 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })
        
        # Twitter/X
        if 'twitter' in url.lower() or 'x.com' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://twitter.com/',
                'Origin': 'https://twitter.com',
            })
        
        return opts

    async def download_video(self, url: str) -> Dict:
        """Download principale con RETRY per tutte le piattaforme"""
        
        # Controlla foto Instagram
        if 'instagram' in url.lower() and '/p/' in url.lower():
            is_video = await self.check_if_video(url)
            if not is_video:
                return {
                    'success': False,
                    'error': '📸 Questo è un POST/FOTO Instagram, non un video!'
                }
        
        # ===== RETRY LOOP - 3 TENTATIVI =====
        for attempt in range(self.max_retries):
            try:
                clean_url = self.clean_url(url)
                platform = self.detect_platform(clean_url)
                
                logger.info(f"Tentativo {attempt + 1}/{self.max_retries} per {platform}: {clean_url}")
                
                # Estrai info
                info = await self.extract_info(clean_url, attempt)
                if not info:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.info(f"Info extraction fallita. Retry {attempt + 1} dopo {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        return {
                            'success': False,
                            'error': self.get_error_message_for_platform(platform, 'extraction_failed')
                        }
                
                # Download
                file_path = await self.download_with_ytdlp(clean_url, attempt)
                if not file_path or not os.path.exists(file_path):
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.info(f"Download fallito. Retry {attempt + 1} dopo {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        return {
                            'success': False,
                            'error': self.get_error_message_for_platform(platform, 'download_failed')
                        }
                
                # Estrai uploader
                uploader = info.get('uploader', 'Sconosciuto')
                if not uploader or uploader == 'Sconosciuto':
                    uploader = info.get('channel', info.get('creator', 'Utente Anonimo'))
                
                logger.info(f"✅ Download riuscito al tentativo {attempt + 1}")
                return {
                    'success': True,
                    'file_path': file_path,
                    'title': info.get('title', 'Video'),
                    'uploader': uploader,
                    'duration': info.get('duration', 0),
                    'platform': platform,
                    'url': clean_url
                }
            
            except Exception as e:
                error_str = str(e).lower()
                logger.error(f"Tentativo {attempt + 1} eccezione: {str(e)[:200]}")
                
                # Gestisci errori specifici
                if 'sign in' in error_str or 'bot' in error_str:
                    return {
                        'success': False,
                        'error': '🤖 YouTube chiede autenticazione (bot detection). Riprova tra poco.'
                    }
                elif 'cannot parse' in error_str or 'parse' in error_str:
                    return {
                        'success': False,
                        'error': '⚠️ Facebook ha cambiato struttura. Riprova con un altro reel.'
                    }
                elif 'no video formats found' in error_str:
                    return {
                        'success': False,
                        'error': '🔒 Video privato o inaccessibile.'
                    }
                
                # Retry
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"Attesa {delay}s prima del tentativo {attempt + 2}")
                    await asyncio.sleep(delay)
        
        # Tutti i tentativi esauriti
        return {
            'success': False,
            'error': '❌ Download fallito dopo 3 tentativi. Riprova più tardi.'
        }

    async def check_if_video(self, url: str) -> bool:
        """Verifica se è video o foto Instagram"""
        try:
            loop = asyncio.get_event_loop()
            
            def _check():
                opts = self.get_ydl_opts(url)
                opts['skip_download'] = True
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    return any(f.get('vcodec') != 'none' for f in formats)
            
            return await loop.run_in_executor(None, _check)
        except:
            return True

    async def extract_info(self, url: str, attempt: int = 0) -> Optional[Dict]:
        """Estrae info video"""
        try:
            opts = self.get_ydl_opts(url, attempt)
            opts['skip_download'] = True
            loop = asyncio.get_event_loop()
            
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract)
            return info
        
        except Exception as e:
            logger.error(f"Extract info attempt {attempt}: {str(e)[:200]}")
            
            # Fallback per YouTube con user-agent diverso
            if 'youtube' in url.lower() and attempt < 2:
                try:
                    opts = self.get_ydl_opts(url, attempt + 1)
                    opts['skip_download'] = True
                    loop = asyncio.get_event_loop()
                    
                    def _extract_alt():
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            return ydl.extract_info(url, download=False)
                    
                    info = await loop.run_in_executor(None, _extract_alt)
                    return info
                except:
                    pass
            
            return None

    async def download_with_ytdlp(self, url: str, attempt: int = 0) -> Optional[str]:
        """Download con yt-dlp"""
        try:
            opts = self.get_ydl_opts(url, attempt)
            loop = asyncio.get_event_loop()
            
            def _download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                    info = ydl.extract_info(url, download=False)
                    filename = ydl.prepare_filename(info)
                    return filename
            
            filename = await loop.run_in_executor(None, _download)
            
            if os.path.exists(filename):
                return filename
            
            # Cerca con estensioni alternative
            base = os.path.splitext(filename)[0]
            for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv']:
                test_file = base + ext
                if os.path.exists(test_file):
                    return test_file
            
            return None
        
        except Exception as e:
            logger.error(f"Download attempt {attempt}: {str(e)[:200]}")
            return None

    def clean_url(self, url: str) -> str:
        """Pulisce URL"""
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
            except:
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
            except:
                pass
        
        # Rimuovi parametri
        if '?' in url:
            url = url.split('?')[0]
        
        return url

    def detect_platform(self, url: str) -> str:
        """Rileva piattaforma"""
        url_lower = url.lower()
        
        if 'tiktok' in url_lower:
            return 'tiktok'
        elif 'instagram' in url_lower or 'ig.tv' in url_lower:
            return 'instagram'
        elif 'facebook' in url_lower or 'fb.' in url_lower:
            return 'facebook'
        elif 'youtube' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'twitter' in url_lower or 'x.com' in url_lower:
            return 'twitter'
        
        return 'unknown'

    def get_error_message_for_platform(self, platform: str, error_type: str) -> str:
        """Messaggio errore personalizzato per piattaforma"""
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
                'download_failed': '📸 Non riesco a scaricare il video Instagram.',
            },
            'tiktok': {
                'extraction_failed': '⚠️ Errore nel caricamento da TikTok.',
                'download_failed': '🔒 Video TikTok non disponibile.',
            },
            'twitter': {
                'extraction_failed': '⚠️ Errore nel caricamento da Twitter/X.',
                'download_failed': '🔒 Video Twitter/X non disponibile.',
            }
        }
        
        return messages.get(platform, {}).get(error_type, '❌ Errore nel download.')
