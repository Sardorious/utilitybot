#!/usr/bin/env python3
"""
FFmpeg-Powered Audio Cleaner
============================
High-performance audio cleaning engine using native FFmpeg filters.
Designed for low-memory VPS environments (Uses < 100MB RAM).

Functions:
- Downloads audio from YouTube (yt-dlp)
- De-noises using FFT algorithm (afftdn)
- Filters frequencies (highpass/lowpass)
- Normalizes loudness (EBU R128 loudnorm)
"""

import os
import sys
import logging
import tempfile
import subprocess
import shutil
import time
import re
from pathlib import Path
import yt_dlp

# ─── Konfiguratsiya ─────────────────────────────────────────────────────
# FFmpeg Engine sozlamalari
NOISE_REDUCE_STRENGTH = 0.6  # Shovqin kamaytirish kuchi (0.0 - 1.0)
TARGET_LOUDNESS = -16.0      # LUFS maqsadli balandlik (podcast standarti)
HIGHPASS_FREQ = 80           # Past chastotali shovqinni kesish (Hz)
LOWPASS_FREQ = 12000         # Yuqori chastotali shovqinni kesish (Hz)

def check_ffmpeg():
    """Check if FFmpeg and FFprobe are installed"""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("FFmpeg or FFprobe not found in system PATH.")

def format_time(seconds: float) -> str:
    """Format seconds into readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"

def get_audio_duration(filepath: str) -> float:
    """Get audio duration using FFprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        return float(output)
    except Exception:
        return 0.0

def download_audio(url: str, output_dir: str, progress_callback=None) -> str:
    """Download audio from YouTube using yt-dlp"""
    logging.info(f"Downloading from YouTube: {url}")
    output_template = os.path.join(output_dir, "raw_audio.%(ext)s")
    
    def ydl_progress_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            try:
                p = d.get('_percent_str', '0%').replace('%','').strip()
                percent = float(p)
                # Download phase: 0% to 30%
                progress_callback(percent * 0.3)
            except:
                pass

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '0',
        }],
        'outtmpl': output_template,
        'noplaylist': True,
        'progress_hooks': [ydl_progress_hook],
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    # Locate the downloaded file
    for f in os.listdir(output_dir):
        if f.startswith("raw_audio"):
            return os.path.join(output_dir, f)
    
    raise FileNotFoundError("Downloaded file not found.")

def process_audio_ffmpeg(input_path: str, output_path: str, progress_callback=None) -> bool:
    """
    Clean audio using streaming FFmpeg filters.
    Extremely RAM efficient as it doesn't load whole file.
    """
    duration = get_audio_duration(input_path)
    if duration <= 0:
        logging.error("Could not determine audio duration.")
        return False

    # Filter chain:
    # 1. afftdn: FFT Denoise
    # 2. highpass/lowpass: Cleanup
    # 3. loudnorm: Normalization
    nr_val = NOISE_REDUCE_STRENGTH * 10 + 10 # Scale strength
    filter_chain = (
        f"afftdn=nr={nr_val}:nf=-30, "
        f"highpass=f={HIGHPASS_FREQ}, lowpass=f={LOWPASS_FREQ}, "
        f"loudnorm=I={TARGET_LOUDNESS}:TP=-1.5:LRA=11"
    )

    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-af', filter_chain,
        '-ar', '44100', '-ac', '1',
        output_path
    ]

    logging.info(f"Starting FFmpeg cleanup. Filters: {filter_chain}")
    
    # Monitor progress from stderr
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
        universal_newlines=True, encoding='utf-8'
    )

    time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
    
    try:
        for line in process.stdout:
            match = time_regex.search(line)
            if match and progress_callback:
                h, m, s = map(int, match.groups())
                curr = h * 3600 + m * 60 + s
                pct = min(100, (curr / duration) * 100)
                # Cleanup phase: 30% to 100%
                progress_callback(30 + (pct * 0.7))
        
        process.wait()
        return process.returncode == 0
    except Exception as e:
        logging.error(f"FFmpeg error: {e}")
        if process: process.kill()
        return False

def process_video(url: str, output_path: str, fmt: str = "mp3", noise_strength: float = 0.6, progress_callback=None) -> str:
    """Main function to clean YouTube audio"""
    check_ffmpeg()
    
    global NOISE_REDUCE_STRENGTH
    NOISE_REDUCE_STRENGTH = noise_strength
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 1. Check duration before downloading
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0)
                if duration > 5400: # 1.5 hours
                    logging.warning(f"Video too long for audio cleaning: {duration}s")
                    return ""

            # 2. Download
            logging.info(f"Download started for: {url}")
            raw_path = download_audio(url, temp_dir, progress_callback)
            
            # 2. Process
            logging.info("Switching to FFmpeg cleanup engine...")
            if progress_callback: progress_callback(30)
            
            success = process_audio_ffmpeg(raw_path, output_path, progress_callback)
            
            if success and os.path.exists(output_path):
                if progress_callback: progress_callback(100)
                return output_path
            return ""
        except Exception as e:
            logging.error(f"Failed to process video: {e}")
            return ""

if __name__ == "__main__":
    # Simple CLI test mode
    if len(sys.argv) > 1:
        logging.basicConfig(level=logging.INFO)
        url = sys.argv[1]
        process_video(url, "out.mp3")
