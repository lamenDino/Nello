#!/usr/bin/env python3
"""
Social Media Downloader v3.4 - FIXATO Facebook URL schema bug
- Corregge URL senza https:// (aggiunge schema automatico)
- Supporta link /share/ di Facebook
- Direct extraction con regex
- Instagram, YouTube, TikTok con yt-dlp
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
from urllib.parse import urlparse

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
            'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
        ]
        
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
    
    def fix_facebook_url_scheme(self, url: str) -> str:
        """Aggiunge https:// se manca (schema incompleto)"""
        if url.startswith('//'):
            return 'https:' + url
        elif not url.startswith('http'):
            return 'https://' + url
        return url
    
    def get_ydl_opts(self, url: str, attempt: int = 0) -> Dict:
        """Ottiene opzioni yt-dlp per piattaforma"""
        opts = self.base_opts.copy()
        
        # Headers universali
        opts['http_headers'] = {
            'User-Agent': self.get_random_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # Instagram
        if 'instagram' in url.lower():
            if os.path.exists(self.instagram_cookies):
                opts['cookiefile'] = self.instagram_cookies
                logger.info("Instagram: usando cookies")
        
        # YouTube
        if 'youtube' in url.lower() or 'youtu.be' in url.lower():
            opts['match_filters'] = ['duration<=60']
            
            if attempt == 0 and os.path.exists(self.youtube_cookies):
                opts['cookiefile'] = self.youtube_cookies
                logger.info("YouTube: usando cookies")
            
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })
        
        # TikTok
        if 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })
        
        return opts
    
    async def extract_facebook_direct(self, url: str) -> Optional[Dict]:
        """Estrae video Facebook direttamente"""
        try:
            logger.info(f"Facebook direct extraction: {url}")
            
            headers = {
                'User-Agent': self.get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://www.facebook.com/',
            }
            
            loop = asyncio.get_event_loop()
            
            def _extract():
                try:
                    # Risolvi URL /share/ prima
                    final_url = url
                    if '/share/' in url.lower():
                        try:
                            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
                            final_url = response.url
                            logger.info(f"URL /share/ risolto: {final_url}")
                        except:
                            pass
                    
                    # Scarica la pagina
                    response = requests.get(final_url, headers=headers, timeout=15)
                    response.raise_for_status()
                    
                    html = response.text
                    
                    # Patterns per trovare il video
                    video_patterns = [
                        # Pattern 1: video_url
                        r'"video_url":"([^"]+\.mp4[^"]*)"',
                        r'"video_url":"([^"\\]+(?:\\/[^"\\]*)?)"',
                        
                        # Pattern 2: src per video
                        r'"src":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"src":"(//[^"]+\.mp4[^"]*)"',
                        
                        # Pattern 3: URL generico
                        r'"url":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"url":"(//[^"]+\.mp4[^"]*)"',
                        
                        # Pattern 4: Direct video element
                        r'<video[^>]+src="([^"]+\.mp4)"',
                        r'<source[^>]+src="([^"]+\.mp4)"',
                    ]
                    
                    for pattern in video_patterns:
                        matches = re.findall(pattern, html)
                        if matches:
                            video_url = matches[0]
                            
                            # Unescape URL
                            video_url = video_url.replace('\\/', '/').replace('\\', '')
                            
                            # FIX: Aggiungi https:// se manca
                            video_url = self._fix_url_scheme(video_url)
                            
                            # Valida URL
                            if video_url.startswith('http'):
                                logger.info(f"Trovato video URL: {video_url[:80]}...")
                                
                                return {
                                    'url': video_url,
                                    'title': 'Facebook Reel',
                                    'uploader': 'Facebook User',
                                    'duration': 0,
                                }
                    
                    logger.warning("Nessun video trovato nella pagina")
                    return None
                
                except Exception as e:
                    logger.error(f"Facebook extraction error: {e}")
                    return None
            
            result = await loop.run_in_executor(None, _extract)
            return result
        
        except Exception as e:
            logger.error(f"Facebook extraction failed: {e}")
            return None
    
    def _fix_url_scheme(self, url: str) -> str:
        """Fissa URL senza schema"""
        url = url.strip()
        
        # Se inizia con //, aggiungi https:
        if url.startswith('//'):
            url = 'https:' + url
        
        # Se non ha schema, aggiungi https://
        elif not url.startswith('http'):
            url = 'https://' + url
        
        return url
    
    async def download_facebook_direct(self, video_url: str) -> Optional[str]:
        """Scarica video Facebook direttamente"""
        try:
            logger.info(f"Scaricando video Facebook...")
            
            # Fissa URL se necessario
            video_url = self._fix_url_scheme(video_url)
            
            headers = {
                'User-Agent': self.get_random_user_agent(),
                'Referer': 'https://www.facebook.com/',
                'Range': 'bytes=0-',
            }
            
            loop = asyncio.get_event_loop()
            
            def _download():
                try:
                    response = requests.get(video_url, headers=headers, timeout=30, stream=True)
                    response.raise_for_status()
                    
                    # Salva il file
                    filename = os.path.join(
                        self.temp_dir,
                        f'facebook_video_{int(__import__("time").time())}.mp4'
                    )
                    
                    with open(filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    logger.info(f"Facebook video salvato: {filename}")
                    return filename
                
                except Exception as e:
                    logger.error(f"Errore download Facebook: {e}")
                    return None
            
            result = await loop.run_in_executor(None, _download)
            return result
        
        except Exception as e:
            logger.error(f"Facebook download error: {e}")
            return None
    
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
        
        # SPECIAL HANDLING per Facebook
        if 'facebook' in url.lower():
            logger.info("Facebook detected - using direct extraction method")
            
            # Prova metodo diretto
            info = await self.extract_facebook_direct(url)
            if info:
                file_path = await self.download_facebook_direct(info['url'])
                if file_path and os.path.exists(file_path):
                    return {
                        'success': True,
                        'file_path': file_path,
                        'title': info.get('title', 'Facebook Reel'),
                        'uploader': info.get('uploader', 'Facebook User'),
                        'duration': info.get('duration', 0),
                        'platform': 'facebook',
                        'url': url
                    }
            
            # Se fallisce
            return {
                'success': False,
                'error': '⚠️ Reel Facebook non disponibile. Potrebbe essere privato o protetto.'
            }
        
        # Per altre piattaforme: retry loop standard
        for attempt in range(self.max_retries):
            try:
                clean_url = self.clean_url(url)
                platform = self.detect_platform(clean_url)
                
                logger.info(f"Tentativo {attempt + 1}/{self.max_retries} per {platform}")
                
                # Estrai info
                info = await self.extract_info(clean_url, attempt)
                if not info:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.info(f"Retry {attempt + 1} dopo {delay}s")
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
                        logger.info(f"Download retry {attempt + 1} dopo {delay}s")
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
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        return {
            'success': False,
            'error': 'Download fallito dopo multiple tentativi. Riprova più tardi.'
        }
    
    async def check_if_video(self, url: str) -> bool:
        """Verifica se è video Instagram"""
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
        """Estrai info video"""
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
            
            # Fallback per YouTube
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
        }
        
        return messages.get(platform, {}).get(error_type, '❌ Errore nel download.')
