#!/usr/bin/env python3
"""
Social Media Downloader v4.3.1 FINAL - FACEBOOK REGEX FALLBACK
- Facebook: yt-dlp come principale
- Se yt-dlp fallisce → Fallback a regex extraction (HTML parsing)
- TikTok caroselli foto SUPPORTATI
- Instagram caroselli SUPPORTATI
"""

import os
import asyncio
import logging
import tempfile
import re
import json
from typing import Dict, Optional, List, Tuple
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
    
    def validate_and_detect_unsupported(self, url: str) -> Tuple[bool, Optional[str], bool]:
        """Valida URL e rileva tipi non supportati"""
        url_lower = url.lower()
        
        # TikTok: caroselli foto - SUPPORTATI
        if 'tiktok' in url_lower and '/photo/' in url_lower:
            return True, None, True
        
        # TikTok: collezioni
        if 'tiktok' in url_lower and '/collection/' in url_lower:
            return False, '📚 Collezione TikTok non supportata.', False
        
        # Instagram: caroselli - SUPPORTATI
        if 'instagram' in url_lower and ('/carousel/' in url_lower or 'carousel' in url_lower):
            return True, None, True
        
        # YouTube: playlist
        if 'youtube' in url_lower and 'playlist' in url_lower:
            return False, '📺 Playlist YouTube non supportate.', False
        
        # YouTube: channel
        if 'youtube' in url_lower and (url_lower.endswith('/@') or '/channel/' in url_lower):
            return False, '📺 Channel YouTube non supportato.', False
        
        # Facebook: OK
        if 'facebook' in url_lower or 'fb.' in url_lower:
            return True, None, False
        
        # URL vuoto
        if not url or len(url) < 10:
            return False, '❌ URL non valido.', False
        
        return True, None, False
    
    async def extract_carousel_items(self, url: str) -> Optional[List[str]]:
        """Estrae gli URL di tutte le foto/video dal carosello"""
        try:
            platform = 'TikTok' if 'tiktok' in url.lower() else 'Instagram'
            logger.info(f"Estrazione carosello {platform}: {url}")
            
            loop = asyncio.get_event_loop()
            
            def _extract():
                try:
                    opts = self.base_opts.copy()
                    opts['extract_flat'] = 'in_playlist'
                    opts['quiet'] = True
                    
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        
                        if 'entries' in info:
                            urls = []
                            for item in info['entries']:
                                if item:
                                    urls.append(item.get('url') or item.get('id'))
                            logger.info(f"Trovate {len(urls)} item nel carosello {platform}")
                            return urls
                    
                    return None
                except Exception as e:
                    logger.error(f"Errore estrazione carosello: {e}")
                    return None
            
            result = await loop.run_in_executor(None, _extract)
            return result
        
        except Exception as e:
            logger.error(f"Carousel extraction failed: {e}")
            return None
    
    async def download_carousel_items(self, carousel_urls: List[str], platform: str = 'generic') -> Optional[List[Dict]]:
        """Scarica tutti i file del carosello"""
        try:
            logger.info(f"Download {len(carousel_urls)} item da carosello {platform}...")
            
            files = []
            
            for idx, item_url in enumerate(carousel_urls[:10]):
                try:
                    logger.info(f"Scaricando item {idx + 1}/{len(carousel_urls)}")
                    
                    loop = asyncio.get_event_loop()
                    
                    def _download_item():
                        try:
                            opts = self.base_opts.copy()
                            
                            def _download():
                                with yt_dlp.YoutubeDL(opts) as ydl:
                                    ydl.download([item_url])
                                    info = ydl.extract_info(item_url, download=False)
                                    filename = ydl.prepare_filename(info)
                                    is_video = 'vcodec' in info and info['vcodec'] != 'none'
                                    return filename, is_video
                            
                            filename, is_video = _download()
                            
                            if os.path.exists(filename):
                                file_type = 'video' if is_video else 'photo'
                                files.append({'path': filename, 'type': file_type})
                                logger.info(f"Item {idx + 1} scaricato: {file_type}")
                        except Exception as e:
                            logger.warning(f"Errore download item {idx + 1}: {e}")
                    
                    await loop.run_in_executor(None, _download_item)
                
                except Exception as e:
                    logger.warning(f"Errore processing item {idx + 1}: {e}")
            
            if files:
                logger.info(f"Totale file scaricati: {len(files)}")
                return files
            
            return None
        
        except Exception as e:
            logger.error(f"Carousel download failed: {e}")
            return None
    
    async def extract_facebook_video_url_regex(self, url: str) -> Optional[str]:
        """Fallback: Estrae video URL da Facebook usando regex (HTML parsing)"""
        try:
            logger.info(f"Facebook regex fallback: {url}")
            
            loop = asyncio.get_event_loop()
            
            def _extract():
                try:
                    response = requests.get(
                        url,
                        headers=self.facebook_headers,
                        timeout=15,
                        allow_redirects=True
                    )
                    response.raise_for_status()
                    
                    html = response.text
                    
                    # Patterns per trovare video URL
                    patterns = [
                        r'<source[^>]+src="([^"]+\.mp4[^"]*)"',
                        r'<video[^>]+src="([^"]+\.mp4)"',
                        r'"src":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"url":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"video_url":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"hd_src":"(https?://[^"]+\.mp4[^"]*)"',
                        r'"videoData":\{"url":"(https?://[^"]+\.mp4)',
                        r'"playableUrl":"(https?://[^"]+\.mp4)',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, html)
                        if matches:
                            for video_url in matches:
                                video_url = video_url.replace('\\/', '/').replace('\\', '')
                                
                                if video_url.startswith('//'):
                                    video_url = 'https:' + video_url
                                elif not video_url.startswith('http'):
                                    video_url = 'https://' + video_url
                                
                                if video_url.startswith('http') and '.mp4' in video_url:
                                    logger.info(f"Trovato video URL (regex): {video_url[:80]}...")
                                    return video_url
                    
                    logger.warning("Nessun video trovato con regex")
                    return None
                
                except Exception as e:
                    logger.error(f"Errore regex extraction: {e}")
                    return None
            
            result = await loop.run_in_executor(None, _extract)
            return result
        
        except Exception as e:
            logger.error(f"Facebook regex fallback failed: {e}")
            return None
    
    async def download_facebook_video(self, video_url: str) -> Optional[str]:
        """Scarica il video Facebook direttamente"""
        try:
            logger.info(f"Scaricando video Facebook...")
            
            loop = asyncio.get_event_loop()
            
            def _download():
                try:
                    response = requests.get(
                        video_url,
                        headers=self.facebook_headers,
                        timeout=60,
                        stream=True
                    )
                    response.raise_for_status()
                    
                    filename = os.path.join(
                        self.temp_dir,
                        f'facebook_video_{int(__import__("time").time())}.mp4'
                    )
                    
                    with open(filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    logger.info(f"Video salvato: {filename}")
                    return filename
                
                except Exception as e:
                    logger.error(f"Errore download: {e}")
                    return None
            
            result = await loop.run_in_executor(None, _download)
            return result
        
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
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
            
            opts['http_headers'].update({
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            })
        
        # Facebook: Opzioni speciali
        if platform == 'facebook' or 'facebook' in url.lower():
            opts['format'] = 'best/worst'
            opts['socket_timeout'] = 60
            opts['no_check_certificates'] = True
            opts['http_headers'].update({
                'Referer': 'https://www.facebook.com/',
                'Origin': 'https://www.facebook.com',
            })
        
        # TikTok
        if platform == 'tiktok' or 'tiktok' in url.lower():
            opts['http_headers'].update({
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            })
        
        return opts
    
    async def download_video(self, url: str) -> Dict:
        """Download principale"""
        
        # VALIDAZIONE
        is_valid, error_msg, is_carousel = self.validate_and_detect_unsupported(url)
        if not is_valid:
            return {'success': False, 'error': error_msg}
        
        # Foto Instagram check
        if 'instagram' in url.lower() and '/p/' in url.lower() and not is_carousel:
            is_video = await self.check_if_video(url)
            if not is_video:
                return {'success': False, 'error': '📸 Questo è un POST/FOTO Instagram!'}
        
        # Determina piattaforma
        platform = self.detect_platform(url)
        
        # Pulisci URL
        clean_url = await self.clean_url_async(url)
        logger.info(f"URL finale: {clean_url}")
        
        # CAROSELLO (Instagram + TikTok /photo/)
        if is_carousel:
            logger.info(f"Carosello rilevato ({platform}) - estrazione items...")
            
            carousel_urls = await self.extract_carousel_items(clean_url)
            if carousel_urls:
                carousel_files = await self.download_carousel_items(carousel_urls, platform)
                if carousel_files:
                    return {
                        'success': True,
                        'file_path': None,
                        'files': carousel_files,
                        'title': f'Carosello ({len(carousel_files)} item)',
                        'uploader': 'Carosello',
                        'duration': 0,
                        'platform': platform,
                        'url': clean_url,
                        'is_carousel': True
                    }
            
            return {'success': False, 'error': '⚠️ Errore estrazione carosello.'}
        
        # FACEBOOK: Tenta yt-dlp, fallback a regex
        if platform == 'facebook':
            logger.info("Facebook - tentando yt-dlp...")
            
            # Tenta yt-dlp prima
            for attempt in range(2):
                try:
                    info = await self.extract_info(clean_url, attempt, platform)
                    if info:
                        file_path = await self.download_with_ytdlp(clean_url, attempt, platform)
                        if file_path and os.path.exists(file_path):
                            uploader = info.get('uploader', 'Sconosciuto')
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
                    logger.warning(f"yt-dlp fallito: {e}")
            
            # Fallback: Regex extraction
            logger.info("Facebook - usando regex fallback...")
            video_url = await self.extract_facebook_video_url_regex(clean_url)
            if video_url:
                file_path = await self.download_facebook_video(video_url)
                if file_path and os.path.exists(file_path):
                    return {
                        'success': True,
                        'file_path': file_path,
                        'title': 'Facebook Video',
                        'uploader': 'Facebook User',
                        'duration': 0,
                        'platform': platform,
                        'url': clean_url
                    }
            
            return {'success': False, 'error': '⚠️ Reel Facebook non disponibile o privato.'}
        
        # DOWNLOAD STANDARD (per gli altri)
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Tentativo {attempt + 1}/{self.max_retries} per {platform}")
                
                info = await self.extract_info(clean_url, attempt, platform)
                if not info:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return {'success': False, 'error': self.get_error_message_for_platform(platform, 'extraction_failed')}
                
                file_path = await self.download_with_ytdlp(clean_url, attempt, platform)
                if not file_path or not os.path.exists(file_path):
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    return {'success': False, 'error': self.get_error_message_for_platform(platform, 'download_failed')}
                
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
                    return {'success': False, 'error': '🤖 YouTube chiede autenticazione.'}
                elif 'no video formats found' in error_str:
                    return {'success': False, 'error': '🔒 Video privato o inaccessibile.'}
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
        
        return {'success': False, 'error': 'Download fallito. Riprova più tardi.'}
    
    async def clean_url_async(self, url: str) -> str:
        """Pulisce URL e risolve redirect"""
        url = url.strip()
        
        if 'facebook.com/share/' in url.lower():
            try:
                loop = asyncio.get_event_loop()
                
                def _resolve():
                    try:
                        response = requests.head(url, allow_redirects=True, timeout=10, headers=self.facebook_headers)
                        return response.url
                    except:
                        return url
                
                url = await loop.run_in_executor(None, _resolve)
                logger.info(f"URL /share/ risolto a: {url}")
            except:
                pass
        
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                loop = asyncio.get_event_loop()
                
                def _resolve_tiktok():
                    try:
                        response = requests.head(url, allow_redirects=True, timeout=10)
                        return response.url
                    except:
                        return url
                
                url = await loop.run_in_executor(None, _resolve_tiktok)
            except:
                pass
        
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
            
            base = os.path.splitext(filename)[0]
            for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.jpg', '.png']:
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
                'extraction_failed': '🤖 YouTube chiede autenticazione.',
                'download_failed': '⚠️ Non riesco a scaricare lo short.',
            },
            'instagram': {
                'extraction_failed': '🔒 Post privato o cookies scaduti.',
                'download_failed': '📸 Non riesco a scaricare il video.',
            },
            'tiktok': {
                'extraction_failed': '⚠️ Video TikTok non disponibile.',
                'download_failed': '🔒 Video TikTok non disponibile.',
            },
            'facebook': {
                'extraction_failed': '⚠️ Reel Facebook non disponibile.',
                'download_failed': '🔒 Reel Facebook non disponibile.',
            },
        }
        
        return messages.get(platform, {}).get(error_type, '❌ Errore nel download.')
