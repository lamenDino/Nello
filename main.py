#!/usr/bin/env python3
"""
Social Media Downloader API v2.2 - COMPLETO
- Fix port 8080
- YouTube reels only (no regular videos)
- Formatted output con emoji, grassetto e NOME UTENTE REALE
- Display user name dinamicamente (non hardcoded)
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import requests
import re
from typing import Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Social Media Downloader API", version="2.2")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Emoji mapping per le piattaforme
PLATFORM_EMOJI = {
    'instagram': '📷',
    'facebook': '👍',
    'tiktok': '🎵',
    'youtube': '▶️',
    'twitter': '🐦',
    'reddit': '🤖',
}

# Frasi simpatiche personalizzabili per i creator
CREATOR_FRASI = {
    # Aggiungi qui i nomi che vuoi con le tue frasi personalizzate
    # Esempio: 'giovanni': 'il monello',
    # Se un creator non è in questa lista, usano il default
}

DEFAULT_FRASI = [
    'l\'esperto del web',
    'l\'artista delle piattaforme',
    'il creatore di contenuti',
    'lo streamer di turno',
    'il maestro dei social',
    'il re dei reel',
]


class SocialMediaDownloader:
    def __init__(self):
        # Get cookies file path
        self.cookies_file = os.path.join(os.path.dirname(__file__), 'instagram_cookies.txt')
        
        self.ydl_opts_instagram = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            'cookiefile': self.cookies_file if os.path.exists(self.cookies_file) else None,
        }
        
        self.ydl_opts_facebook = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
        }
        
        self.ydl_opts_youtube = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            # YouTube: scarica solo Shorts (reels)
            'match_filters': [
                'duration<=60',  # Solo video <= 60 secondi (Shorts)
            ],
        }
        
        self.ydl_opts_tiktok = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
        }
        
        self.ydl_opts_default = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
        }
    
    def fix_facebook_url(self, url: str) -> str:
        """Converte URL Facebook problematici in formato compatibile"""
        if '/share/' in url:
            try:
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                final_url = response.url
                logger.info(f"Facebook URL redirect: {url} -> {final_url}")
                
                match = re.search(r'[?&]v=(\d+)', final_url)
                if match:
                    return f'https://www.facebook.com/watch/?v={match.group(1)}'
                
                match = re.search(r'/reel/(\d+)', final_url)
                if match:
                    return f'https://www.facebook.com/reel/{match.group(1)}'
                
                return final_url
            except Exception as e:
                logger.error(f"Errore conversione URL Facebook: {e}")
                return url
        return url
    
    def get_frase_simpatica(self, username: str) -> str:
        """Ottiene una frase simpatica per il creator (personalizzata o default)"""
        # Se il creator è nella lista personalizzata, usa quella
        if username in CREATOR_FRASI:
            return CREATOR_FRASI[username]
        
        # Altrimenti, usa una frase default random
        import random
        return random.choice(DEFAULT_FRASI)
    
    def format_response(self, info: dict, url: str, platform: str) -> dict:
        """Formatta la risposta con emoji e stile simpatico"""
        
        emoji_platform = PLATFORM_EMOJI.get(platform, '📱')
        emoji_user = '👤'
        emoji_link = '🔗'
        
        # Ottieni l'username dell'uploader DAL VIDEO (non hardcoded!)
        uploader = info.get('uploader', 'Utente Sconosciuto')
        
        # Ottieni una frase simpatica per questo creator
        frase = self.get_frase_simpatica(uploader)
        nome_simpatico = f"{uploader} - {frase}"
        
        # Formatta il risultato con grassetto e emoji
        formatted_result = {
            'success': True,
            'formatted_info': {
                'piattaforma': f"{emoji_platform} **Video da: {platform.upper()}**",
                'uploader': f"{emoji_user} Video inviato da: {nome_simpatico}",
                'link': f"{emoji_link} Link originale: {url}",
            },
            'info': {
                'title': info.get('title', 'Unknown'),
                'url': url,
                'filename': None,  # Viene settato dal downloader
                'duration': info.get('duration', 0),
                'uploader': uploader,  # NOME REALE dell'uploader
                'platform': platform,
                'upload_date': info.get('upload_date', 'sconosciuta'),
                'views': info.get('view_count', 0),
            }
        }
        
        return formatted_result
    
    def is_youtube_short(self, url: str, info: dict) -> bool:
        """Verifica se un video YouTube è uno Short (<= 60 secondi)"""
        duration = info.get('duration', 0)
        
        # Verifica se è uno short (URL contiene /shorts/ o durata <= 60 secondi)
        is_shorts_url = '/shorts/' in url
        is_short_duration = duration and duration <= 60
        
        if is_shorts_url or is_short_duration:
            return True
        
        return False
    
    def download(self, url: str) -> dict:
        """Download universale da social media"""
        try:
            # Validazione URL
            if not url.startswith(('http://', 'https://')):
                raise ValueError("URL deve iniziare con http:// o https://")
            
            # Determina la piattaforma
            if 'instagram.com' in url:
                logger.info(f"Rilevato Instagram: {url}")
                opts = self.ydl_opts_instagram.copy()
                platform = 'instagram'
                if not os.path.exists(self.cookies_file):
                    raise ValueError("Cookies Instagram non trovati. Contatta l'amministratore.")
            
            elif 'facebook.com' in url or 'fb.watch' in url:
                logger.info(f"Rilevato Facebook: {url}")
                url = self.fix_facebook_url(url)
                opts = self.ydl_opts_facebook.copy()
                platform = 'facebook'
            
            elif 'tiktok.com' in url:
                logger.info(f"Rilevato TikTok: {url}")
                opts = self.ydl_opts_tiktok.copy()
                platform = 'tiktok'
            
            elif 'youtube.com' in url or 'youtu.be' in url:
                logger.info(f"Rilevato YouTube: {url}")
                
                # PRIMA ottieni le info per verificare se è uno short
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        if not self.is_youtube_short(url, info):
                            raise ValueError(
                                "⚠️ Questo è un video YouTube normale, non uno Short! "
                                "Scarico solo Shorts (video <= 60 secondi). "
                                f"Durata video: {info.get('duration', 0)} secondi"
                            )
                    except Exception as e:
                        if "not a YouTube Short" not in str(e):
                            logger.error(f"Errore verifica YouTube: {e}")
                        raise
                
                opts = self.ydl_opts_youtube.copy()
                platform = 'youtube'
            
            else:
                logger.info(f"URL generico: {url}")
                opts = self.ydl_opts_default.copy()
                platform = 'generico'
            
            # Download
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Formatta la risposta
                result = self.format_response(info, url, platform)
                result['info']['filename'] = filename
                
                return result
        
        except Exception as e:
            logger.error(f"Errore download: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'url': url,
            }


# Initialize downloader
downloader = SocialMediaDownloader()

# Create downloads directory
os.makedirs('downloads', exist_ok=True)


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": "Social Media Downloader API",
        "version": "2.2",
        "endpoints": {
            "download": "/download?url=YOUR_URL",
            "status": "/status",
            "health": "/health",
        },
        "supported_platforms": {
            "Instagram": "Reels, Posts, Stories",
            "Facebook": "Videos, Reels (incluso /share/)",
            "TikTok": "Tutti i video",
            "YouTube": "Solo Shorts (video <= 60 secondi)",
            "Twitter/X": "Tutti i video",
            "Reddit": "Video e GIF",
        }
    }


@app.get("/download")
async def download_get(url: str):
    """Download endpoint - GET method"""
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter required")
    
    logger.info(f"Download request (GET): {url}")
    result = downloader.download(url)
    
    if result['success']:
        return JSONResponse(status_code=200, content=result)
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/download")
async def download_post(data: dict):
    """Download endpoint - POST method"""
    url = data.get('url')
    
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter required")
    
    logger.info(f"Download request (POST): {url}")
    result = downloader.download(url)
    
    if result['success']:
        return JSONResponse(status_code=200, content=result)
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "Social Media Downloader"}


@app.get("/status")
async def status():
    """Status endpoint"""
    cookies_exists = os.path.exists(downloader.cookies_file)
    try:
        downloads_dir_size = sum(os.path.getsize(os.path.join('downloads', f)) 
                                for f in os.listdir('downloads') 
                                if os.path.isfile(os.path.join('downloads', f))) // (1024*1024)
    except:
        downloads_dir_size = 0
    
    return {
        "status": "running",
        "instagram_cookies": "configured" if cookies_exists else "missing",
        "downloads_dir_size_mb": downloads_dir_size,
        "supported_platforms": {
            "Instagram": "✅ Con autenticazione",
            "Facebook": "✅ Incluso /share/",
            "TikTok": "✅ Tutti i video",
            "YouTube": "✅ Solo Shorts (<=60sec)",
            "Twitter": "✅ Video e GIF",
            "Reddit": "✅ Video e GIF",
        }
    }


if __name__ == "__main__":
    import uvicorn
    # Render assegna la porta automaticamente
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
