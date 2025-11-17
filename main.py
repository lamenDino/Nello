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

app = FastAPI(title="Social Media Downloader API", version="2.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
                # Segui i redirect per ottenere l'URL reale
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                final_url = response.url
                logger.info(f"Facebook URL redirect: {url} -> {final_url}")
                
                # Estrai ID del video
                match = re.search(r'[?&]v=(\d+)', final_url)
                if match:
                    return f'https://www.facebook.com/watch/?v={match.group(1)}'
                
                # Estrai formato reel
                match = re.search(r'/reel/(\d+)', final_url)
                if match:
                    return f'https://www.facebook.com/reel/{match.group(1)}'
                
                return final_url
            except Exception as e:
                logger.error(f"Errore conversione URL Facebook: {e}")
                return url
        return url
    
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
                if not os.path.exists(self.cookies_file):
                    raise ValueError("Cookies Instagram non trovati. Contatta l'amministratore.")
            elif 'facebook.com' in url or 'fb.watch' in url:
                logger.info(f"Rilevato Facebook: {url}")
                url = self.fix_facebook_url(url)
                opts = self.ydl_opts_facebook.copy()
            elif 'tiktok.com' in url:
                logger.info(f"Rilevato TikTok: {url}")
                opts = self.ydl_opts_default.copy()
            elif 'youtube.com' in url or 'youtu.be' in url:
                logger.info(f"Rilevato YouTube: {url}")
                opts = self.ydl_opts_default.copy()
            else:
                logger.info(f"URL generico: {url}")
                opts = self.ydl_opts_default.copy()
            
            # Download
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                return {
                    'success': True,
                    'title': info.get('title', 'Unknown'),
                    'url': url,
                    'filename': ydl.prepare_filename(info),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                }
        
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
        "version": "2.0",
        "endpoints": {
            "download": "/download?url=YOUR_URL",
            "status": "/status",
            "health": "/health",
        }
    }


@app.get("/download")
async def download(url: str):
    """Download endpoint"""
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter required")
    
    logger.info(f"Download request: {url}")
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
    downloads_dir_size = sum(os.path.getsize(os.path.join('downloads', f)) 
                            for f in os.listdir('downloads') 
                            if os.path.isfile(os.path.join('downloads', f))) // (1024*1024)
    
    return {
        "status": "running",
        "instagram_cookies": "configured" if cookies_exists else "missing",
        "downloads_dir_size_mb": downloads_dir_size,
        "supported_platforms": ["Instagram", "Facebook", "TikTok", "YouTube", "Twitter", "Reddit"],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
