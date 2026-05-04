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

def get_video_info(filepath: str) -> dict:
    """Extract width, height, and duration from video file using ffprobe"""
    info = {"width": None, "height": None, "duration": 0.0}
    try:
        # Get duration
        cmd_dur = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        info["duration"] = float(subprocess.check_output(cmd_dur, stderr=subprocess.STDOUT).decode('utf-8').strip())
        
        # Get dimensions
        cmd_dim = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=s=x:p=0', filepath
        ]
        dim_str = subprocess.check_output(cmd_dim, stderr=subprocess.STDOUT).decode('utf-8').strip()
        if 'x' in dim_str:
            w, h = dim_str.split('x')
            info["width"] = int(w)
            info["height"] = int(h)
    except Exception as e:
        logging.error(f"Error getting video info: {e}")
    return info

def compress_video_ffmpeg(input_path: str, output_path: str, progress_callback=None, target_size_mb=48.0) -> bool:
    """Standardize and compress video using ffmpeg for maximum Telegram compatibility"""
    check_ffmpeg()
    
    info = get_video_info(input_path)
    duration = info["duration"]
    
    # Standard compatibility flags for Telegram:
    # -vcodec libx264: H.264 video
    # -profile:v baseline -level 3.0: High compatibility profile
    # -pix_fmt yuv420p: Ensure standard pixel format (fixes black screen)
    # -movflags +faststart: Move metadata to start for instant playback
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-vcodec', 'libx264',
        '-profile:v', 'baseline',
        '-level', '3.0',
        '-pix_fmt', 'yuv420p',
        '-crf', '28', # Balanced quality/size
        '-preset', 'medium',
        '-vf', "scale='trunc(min(720,iw)/2)*2':'trunc(ow/a/2)*2'",
        '-acodec', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        output_path
    ]
    
    # If it's a huge file, use more aggressive compression
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    if file_size_mb > target_size_mb:
        # Find index of crf and update it
        try:
            crf_idx = cmd.index('-crf')
            cmd[crf_idx + 1] = '32'
            preset_idx = cmd.index('-preset')
            cmd[preset_idx + 1] = 'fast'
        except ValueError:
            pass

    logging.info(f"Starting video processing: {' '.join(cmd)}")
    
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
    """Download video from URL. Automatically compresses if file > 48MB to avoid Telegram limit."""
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
                
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dl_path = os.path.join(temp_dir, "temp_vid.mp4")
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best',
            'outtmpl': temp_dl_path,
            'noplaylist': True,
            'progress_hooks': [ydl_progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        
        if os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            found_path = temp_dl_path
            for f in os.listdir(temp_dir):
                if f.startswith("temp_vid"):
                    found_path = os.path.join(temp_dir, f)
                    break
                    
            if not os.path.exists(found_path):
                return ""
            
            # ALWAYS standardize/compress video to ensure 100% Telegram compatibility
            if progress_callback:
                progress_callback(50.0) # signal start of processing
            
            def compress_hook(pct):
                if progress_callback:
                    progress_callback(50.0 + (pct * 0.5))
                    
            success = compress_video_ffmpeg(found_path, output_path, compress_hook)
            if success and os.path.exists(output_path):
                return output_path
            return ""
                
        except Exception as e:
            logging.error(f"Error processing video: {e}")
            return ""
