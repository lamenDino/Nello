#!/usr/bin/env python3
"""
Social Media Downloader v3.6 - FACEBOOK HTTP 400 FIXED
- Aggiunge headers completi per evitare blocco Facebook (400 Bad Request)
- Connection keep-alive, Accept-Encoding, etc.
- Supporto completo per /reel/ e /share/ link
- Instagram, YouTube, TikTok con yt-dlp standard
"""

import os
import asyncio
import logging
import tempfile
import re
from typing import Dict, Optional
import yt_dlp
import requests
import subprocess

logger = logging.getLogger(__name__)

class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        
        # Percorsi cookies
        self.instagram_cookies = os.path.join(os.path.dirname(__file__), 'cookies.txt')
        self.youtube_cookies = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')
        
        # Controlla e aggiorna yt-dlp
        self.check_ytdlp_version()
        
        # User-Agent pool
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1',
        ]
        
        # Headers completi per evitare 400 Bad Request
        self.facebook_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-GPC': '1',
            'Referer': 'https://www.facebook.com/',
        }
        
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            'max_filesize': 50 * 1024 * 1024,
        }
        
        self.max_retries = 3
        self.retry_delay = 2
    
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
            
            logger.info("Aggiornamento yt-dlp...")
            subprocess.run(
                ['pip', 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                timeout=60
            )
        except Exception as e:
            logger.warning(f"Errore check yt-dlp: {e}")
    
    def get_random_user_agent(self) -> str:
        """Ritorna user-agent random"""
        import random
        return random.choice(self.user_agents)
    
    def get_ydl_opts(self, url: str, attempt: int = 0, platform: str = 'generic') -> Dict:
        """Ottiene opzioni yt-dlp per piattaforma"""
        opts = self.base_opts.copy()
        
        # Headers universali
        opts['http_headers'] = {
            'User-Agent': self.get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # Instagram
        if platform == 'instagram' or 'instagram' in url.lower():
            if os.path.exists(self.instagram_cookies):
                opts['cookiefile'] = self.instagram_cookies
                logger.info("Instagram: usando cookies")
        
        # YouTube
        if platform == 'youtube' or 'youtube' in url.lower() or 'youtu.be' in url.lower():
            opts['match_filters'] = ['duration<=60']
            
            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts['cookiefile'] = self.youtube_cookies
                logger.info("YouTube: usando cookies")
            
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })
        
        # Facebook: usa TUTTI gli header corretti per evitare 400
        if platform == 'facebook' or 'facebook' in url.lower():
            # Copia i facebook_headers completi
            opts['http_headers'] = self.facebook_headers.copy()
            # Randomizza User-Agent per questo header
            opts['http_headers']['User-Agent'] = self.get_random_user_agent()
            
            # Usa formato generico per evitare parsing bug
            opts['format'] = 'best/worst'
            opts['socket_timeout'] = 45
            
            logger.info("Facebook: usando headers completi")
        
        # TikTok
        if platform == 'tiktok' or 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })
        
        return opts
    
    async def download_video(self, url: str) -> Dict:
        """Download principale"""
        
        # Controlla foto Instagram
        if 'instagram' in url.lower() and '/p/' in url.lower():
            is_video = await self.check_if_video(url)
            if not is_video:
                return {
                    'success': False,
                    'error': '📸 Questo è un POST/FOTO Instagram, non un video!'
                }
        
        # Determina piattaforma
        platform = self.detect_platform(url)
        
        # Pulisci URL (risolvi redirect /share/)
        clean_url = await self.clean_url_async(url)
        logger.info(f"URL finale: {clean_url}")
        
        # Retry loop per tutte le piattaforme
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Tentativo {attempt + 1}/{self.max_retries} per {platform}: {clean_url}")
                
                # Estrai info
                info = await self.extract_info(clean_url, attempt, platform)
                if not info:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.info(f"Retry info {attempt + 1} dopo {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        return {
                            'success': False,
                            'error': self.get_error_message_for_platform(platform, 'extraction_failed')
                        }
                
                # Download
                file_path = await self.download_with_ytdlp(clean_url, attempt, platform)
                if not file_path or not os.path.exists(file_path):
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.info(f"Retry download {attempt + 1} dopo {delay}s")
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
                logger.error(f"Tentativo {attempt + 1} fallito: {str(e)[:200]}")
                
                if 'sign in' in error_str or 'bot' in error_str:
                    return {
                        'success': False,
                        'error': '🤖 YouTube chiede autenticazione. Riprova tra poco.'
                    }
                elif 'no video formats found' in error_str:
                    return {
                        'success': False,
                        'error': '🔒 Video privato o inaccessibile.'
                    }
                elif '400' in error_str or 'bad request' in error_str:
                    logger.warning("HTTP 400 Bad Request - Facebook blocking? Retrying...")
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        return {
            'success': False,
            'error': 'Download fallito dopo multiple tentativi. Riprova più tardi.'
        }
    
    async def clean_url_async(self, url: str) -> str:
        """Pulisce URL e risolve redirect (async)"""
        url = url.strip()
        
        # Facebook /share/ - risolvi redirect
        if 'facebook.com/share/' in url.lower():
            try:
                loop = asyncio.get_event_loop()
                
                def _resolve():
                    try:
                        response = requests.head(
                            url,
                            allow_redirects=True,
                            timeout=10,
                            headers=self.facebook_headers
                        )
                        return response.url
                    except:
                        return url
                
                url = await loop.run_in_executor(None, _resolve)
                logger.info(f"URL /share/ risolto a: {url}")
            except:
                pass
        
        # TikTok short URLs
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                loop = asyncio.get_event_loop()
                
                def _resolve_tiktok():
                    try:
                        response = requests.head(
                            url,
                            allow_redirects=True,
                            timeout=10,
                            headers={'User-Agent': self.get_random_user_agent()}
                        )
                        return response.url
                    except:
                        return url
                
                url = await loop.run_in_executor(None, _resolve_tiktok)
            except:
                pass
        
        # Rimuovi parametri query
        if '?' in url:
            url = url.split('?')[0]
        
        return url
    
    async def check_if_video(self, url: str) -> bool:
        """Verifica se è video Instagram"""
        try:
            loop = asyncio.get_event_loop()
            
            def _check():
                opts = self.get_ydl_opts(url, platform='instagram')
                opts['skip_download'] = True
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    return any(f.get('vcodec') != 'none' for f in formats)
            
            return await loop.run_in_executor(None, _check)
        except:
            return True
    
    async def extract_info(self, url: str, attempt: int = 0, platform: str = 'generic') -> Optional[Dict]:
        """Estrai info video"""
        try:
            opts = self.get_ydl_opts(url, attempt, platform)
            opts['skip_download'] = True
            
            loop = asyncio.get_event_loop()
            
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract)
            return info
        
        except Exception as e:
            logger.error(f"Extract info attempt {attempt}: {str(e)[:200]}")
            
            # Fallback per YouTube
            if platform == 'youtube' and attempt < 2:
                try:
                    opts = self.get_ydl_opts(url, attempt + 1, 'youtube')
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
    
    async def download_with_ytdlp(self, url: str, attempt: int = 0, platform: str = 'generic') -> Optional[str]:
        """Download con yt-dlp"""
        try:
            opts = self.get_ydl_opts(url, attempt, platform)
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
            for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v']:
                test_file = base + ext
                if os.path.exists(test_file):
                    return test_file
            
            return None
        
        except Exception as e:
            logger.error(f"Download attempt {attempt}: {str(e)[:200]}")
            return None
    
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
        return 'generic'
    
    def get_error_message_for_platform(self, platform: str, error_type: str) -> str:
        """Messaggio errore per piattaforma"""
        messages = {
            'youtube': {
                'extraction_failed': '🤖 YouTube chiede autenticazione. Riprova tra poco.',
                'download_failed': '⚠️ Non riesco a scaricare lo short. Riprova.',
            },
            'instagram': {
                'extraction_failed': '🔒 Post privato o cookies scaduti.',
                'download_failed': '📸 Non riesco a scaricare il video Instagram.',
            },
            'tiktok': {
                'extraction_failed': '⚠️ Errore nel caricamento da TikTok.',
                'download_failed': '🔒 Video TikTok non disponibile.',
            },
            'facebook': {
                'extraction_failed': '⚠️ Reel Facebook non disponibile. Riprova.',
                'download_failed': '🔒 Non riesco a scaricare il reel. Potrebbe essere privato.',
            },
        }
        
        return messages.get(platform, {}).get(error_type, '❌ Errore nel download.')
