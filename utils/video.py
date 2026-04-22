import os
import logging
import yt_dlp

def download_video(url: str, output_path: str, progress_callback=None) -> str:
    """Download video from URL (Instagram, etc) using yt-dlp optimally without heavy CPU usage"""
    logging.info(f"Downloading video from URL: {url}")
    
    def ydl_progress_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            try:
                p = d.get('_percent_str', '0%').replace('%','').strip()
                percent = float(p)
                progress_callback(percent)
            except:
                pass
                
    # Select natively smaller/compressed format from Instagram CDN (max 720p mp4)
    # This avoids using our own VPS CPU to compress it!
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best',
        'outtmpl': output_path,
        'noplaylist': True,
        'progress_hooks': [ydl_progress_hook],
        'quiet': True,
        'no_warnings': True,
    }
    
    # If cookies.txt exists in the project root, use it to bypass 429 requests
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return ""
