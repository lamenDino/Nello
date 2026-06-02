#!/usr/bin/env python3
"""Mixin estratto da social_downloader.py (refactoring per piattaforma).
Contiene metodi che operano su `self` del SocialMediaDownloader."""

import os
import re
import json
import html
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class InstagramMixin:
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

