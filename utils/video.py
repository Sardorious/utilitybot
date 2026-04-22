import os
import logging
import yt_dlp
import subprocess
import shutil
import tempfile
import re

def check_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("FFmpeg is missing.")

def get_video_duration(filepath: str) -> float:
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        return float(subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').strip())
    except Exception:
        return 0.0

def compress_video(input_path: str, output_path: str, progress_callback=None) -> bool:
    """Compress video using ffmpeg ensuring Telegram compatibility and small size"""
    check_ffmpeg()
    
    # Ensure H264 and max 720p, compress bitrate
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-vcodec', 'libx264',
        '-crf', '28',
        '-preset', 'fast',
        '-vf', "scale='trunc(min(720,iw)/2)*2':'trunc(ow/a/2)*2'",
        '-acodec', 'aac',
        '-b:a', '128k',
        output_path
    ]
    
    logging.info(f"Starting video compression: {' '.join(cmd)}")
    duration = get_video_duration(input_path)
    
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
        universal_newlines=True, encoding='utf-8'
    )
    
    time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
    try:
        for line in process.stdout:
            match = time_regex.search(line)
            if match and progress_callback and duration > 0:
                h, m, s = map(int, match.groups())
                curr = h * 3600 + m * 60 + s
                pct = min(100.0, (curr / duration) * 100.0)
                progress_callback(pct)
        process.wait()
        return process.returncode == 0
    except Exception as e:
        logging.error(f"FFmpeg video compression error: {e}")
        if process: process.kill()
        return False

def download_video(url: str, output_path: str, progress_callback=None) -> str:
    """Download video from URL (Instagram, etc) using yt-dlp, then compress it!"""
    logging.info(f"Downloading video from URL: {url}")
    
    def ydl_progress_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            try:
                p = d.get('_percent_str', '0%').replace('%','').strip()
                percent = float(p)
                # Map 0-100 to 0-50 for download phase
                progress_callback(percent * 0.5)
            except:
                pass
                
    # Temporarily download to a temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dl_path = os.path.join(temp_dir, "temp_vid.mp4")
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_dl_path,
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
            
            # File should now exist at temp_dl_path
            found_path = temp_dl_path
            # In case yt-dlp modifies the extension based on actual format
            for f in os.listdir(temp_dir):
                if f.startswith("temp_vid"):
                    found_path = os.path.join(temp_dir, f)
                    break
            
            if not os.path.exists(found_path):
                return ""
                
            # Compress the downloaded video representing 50% to 100% progress
            if progress_callback:
                progress_callback(50.0)
            
            def compress_hook(pct):
                # Map 0-100 to 50-100
                if progress_callback:
                    progress_callback(50.0 + (pct * 0.5))
            
            success = compress_video(found_path, output_path, compress_hook)
            if success and os.path.exists(output_path):
                return output_path
            return ""
        except Exception as e:
            logging.error(f"Error processing video: {e}")
            return ""
