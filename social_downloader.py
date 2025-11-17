#!/usr/bin/env python3
"""
Social Media Downloader v3.0
- Supporta: TikTok, Instagram (reels + posts + storie), Facebook (video + reels + /share/), YouTube (shorts)
- Estrae nome utente reale dell'uploader
- Gestione errori robusta
"""

import os
import asyncio
import logging
import tempfile
import re
from typing import Dict, Optional
import yt_dlp
import requests

logger = logging.getLogger(__name__)

class SocialMediaDownloader:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        
        # Percorso cookies Instagram
        self.cookies_file = os.path.join(
            os.path.dirname(__file__),
            'cookies.txt'
        )
        
        # Opzioni base yt-dlp
        self.base_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title)s_%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            'max_filesize': 50 * 1024 * 1024,  # 50MB max
        }
    
    def get_ydl_opts(self, url: str) -> Dict:
        """Ottiene le opzioni yt-dlp per la piattaforma specifica"""
        opts = self.base_opts.copy()
        
        # Instagram: aggiungi cookies
        if 'instagram' in url.lower():
            if os.path.exists(self.cookies_file):
                opts['cookiefile'] = self.cookies_file
        
        # YouTube: solo Shorts (<=60 secondi)
        if 'youtube' in url.lower() or 'youtu.be' in url.lower():
            opts['match_filters'] = ['duration<=60']
        
        return opts
    
    async def download_video(self, url: str) -> Dict:
        """Download principale"""
        try:
            # Pulisci URL
            clean_url = self.clean_url(url)
            
            # Estrai informazioni
            info = await self.extract_info(clean_url)
            if not info:
                return {
                    'success': False,
                    'error': 'Impossibile estrarre informazioni dal video'
                }
            
            # Download
            file_path = await self.download_with_ytdlp(clean_url)
            if not file_path or not os.path.exists(file_path):
                return {
                    'success': False,
                    'error': 'Download fallito'
                }
            
            # Estrai uploader REALE
            uploader = info.get('uploader', 'Sconosciuto')
            if not uploader or uploader == 'Sconosciuto':
                uploader = info.get('channel', info.get('creator', 'Utente Anonimo'))
            
            return {
                'success': True,
                'file_path': file_path,
                'title': info.get('title', 'Video'),
                'uploader': uploader,
                'duration': info.get('duration', 0),
                'platform': self.detect_platform(clean_url),
                'url': clean_url
            }
        
        except Exception as e:
            logger.error(f"Errore download {url}: {str(e)}")
            return {
                'success': False,
                'error': self.format_error(str(e))
            }
    
    async def extract_info(self, url: str) -> Optional[Dict]:
        """Estrae informazioni dal video"""
        try:
            opts = self.get_ydl_opts(url)
            opts['skip_download'] = True
            
            loop = asyncio.get_event_loop()
            
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract)
            return info
        
        except Exception as e:
            logger.error(f"Errore estrazione info {url}: {str(e)}")
            return None
    
    async def download_with_ytdlp(self, url: str) -> Optional[str]:
        """Download con yt-dlp"""
        try:
            opts = self.get_ydl_opts(url)
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
            
            # Cerca il file con estensioni alternative
            base = os.path.splitext(filename)[0]
            for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                test_file = base + ext
                if os.path.exists(test_file):
                    return test_file
            
            return None
        
        except Exception as e:
            logger.error(f"Errore yt-dlp {url}: {str(e)}")
            return None
    
    def clean_url(self, url: str) -> str:
        """Pulisce e normalizza l'URL"""
        url = url.strip()
        
        # Facebook /share/ → formato diretto
        if 'facebook.com/share/' in url:
            try:
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0'}
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
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                url = response.url
            except:
                pass
        
        # Rimuovi parametri query
        if '?' in url:
            url = url.split('?')[0]
        
        return url
    
    def detect_platform(self, url: str) -> str:
        """Rileva la piattaforma"""
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
    
    def format_error(self, error_msg: str) -> str:
        """Formatta il messaggio d'errore"""
        error_lower = error_msg.lower()
        
        if 'age restricted' in error_lower or 'private' in error_lower:
            return 'Video privato o con restrizioni d\'età'
        elif 'not available' in error_lower:
            return 'Video non disponibile'
        elif 'no video formats found' in error_lower:
            return 'Formato video non supportato'
        elif 'sign in' in error_lower or 'login' in error_lower:
            return 'Richiesta autenticazione (cookies scaduti?)'
        elif 'max_filesize' in error_lower or 'too large' in error_lower:
            return 'Video troppo grande (max 50MB)'
        else:
            return 'Errore nel download. Riprova più tardi.'
