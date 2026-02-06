
import asyncio
import logging
import os
from social_downloader import SocialMediaDownloader

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_extraction():
    urls = [
        "https://www.youtube.com/shorts/uN1a4WdZRCU",
        "https://www.youtube.com/shorts/lBPwEsI4a9g"
    ]
    
    dl = SocialMediaDownloader(debug=True)
    
    # Force loading cookies if present
    dl.facebook_cookies = os.path.abspath('facebook_cookies.txt')
    dl.instagram_cookies = os.path.abspath('cookies.txt')

    print("\n" + "="*50)
    print("STARTING TEST EXTRACTION")
    print("="*50 + "\n")

    for url in urls:
        print(f"\nTesting URL: {url}")
        try:
            result = await dl.download_video(url)
            
            if result and result.get('success'):
                print(f"✅ SUCCESS")
                print(f"   Type: {result.get('type')}")
                print(f"   Title: {result.get('title')}")
                files = result.get('file_path') or result.get('files')
                print(f"   File: {files}")
                # Check for bad files
                if isinstance(files, list):
                    for f in files:
                        if 'static.cdninstagram' in f or 'rsrc.php' in f:
                             print(f"   ⚠️ WARNING: Suspect static file found: {f}")
            else:
                print(f"❌ FAILED")
                print(f"   Error: {result.get('error') if result else 'None'}")
                
        except Exception as e:
            print(f"💥 EXCEPTION: {e}")

    print("\n" + "="*50)
    print("TEST COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_extraction())
