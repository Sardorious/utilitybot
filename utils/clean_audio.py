"""
YouTube Audio Cleaner
=====================
YouTube videolardan ovozni yuklab olib:
  1. Orqa fon shovqinini olib tashlaydi
  2. Ovoz balandligini normallashtiiradi
  3. Nutqni tiniqlashtiradi

Uzun videolar (1 soat+) uchun optimallashtirilgan — bo'laklab qayta ishlash.

Foydalanish:
  python clean_audio.py "https://youtube.com/watch?v=..."
  python clean_audio.py "https://youtube.com/watch?v=..." --output tozalangan.mp3
  python clean_audio.py "https://youtube.com/watch?v=..." --format wav
  python clean_audio.py "https://youtube.com/watch?v=..." --noise-reduce-strength 0.8
"""

import argparse
import os
import sys
import io
import logging

# Majburiy UTF-8 kodlash (Windows terminallarida emoji chiqarish uchun)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import tempfile
import subprocess
import shutil
import time
from pathlib import Path

import numpy as np
if not hasattr(np, 'float'):
    np.float = float
if not hasattr(np, 'complex'):
    np.complex = complex
import soundfile as sf
import librosa
import noisereduce as nr
import pyloudnorm as pyln
from pydub import AudioSegment
from scipy.signal import butter, sosfilt
import yt_dlp


# ─── Konfiguratsiya ─────────────────────────────────────────────────────
SAMPLE_RATE = 44100          # Audio namuna tezligi
TARGET_LOUDNESS = -16.0      # LUFS maqsadli balandlik (podcast standarti)
NOISE_REDUCE_STRENGTH = 0.6  # Shovqin kamaytirish kuchi (0.0 - 1.0)
HIGHPASS_FREQ = 80           # Past chastotali shovqinni kesish (Hz)
LOWPASS_FREQ = 12000         # Yuqori chastotali shovqinni kesish (Hz)

# ─── Chunk konfiguratsiya (uzun videolar uchun) ──────────────────────────
CHUNK_DURATION_SEC = 60      # Har bir bo'lak 1 daqiqa (RAM xavfsizligi darajasi)
OVERLAP_SEC = 2              # Bo'laklar orasida 2 soniyalik overlap (silliq ulanish uchun)
LONG_VIDEO_THRESHOLD = 600   # 10 daqiqadan uzun = bo'laklab ishlash


def check_ffmpeg():
    """FFmpeg o'rnatilganligini tekshirish"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg topilmadi!\n"
            "FFmpeg o'rnating:\n"
            "Ubuntu/Linux: sudo apt update && sudo apt install ffmpeg\n"
            "Windows: winget install FFmpeg\n"
            "yoki: https://ffmpeg.org/download.html"
        )


def format_time(seconds: float) -> str:
    """Soniyani odam o'qiy oladigan formatga o'tkazish"""
    if seconds < 60:
        return f"{seconds:.1f} soniya"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m} daqiqa {s} soniya"
    else:
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        return f"{h} soat {m} daqiqa"


def download_audio(url: str, output_dir: str, progress_callback=None) -> str:
    """YouTube'dan audio yuklab olish"""
    print("\n📥 YouTube'dan audio yuklab olinmoqda...")
    
    output_template = os.path.join(output_dir, "raw_audio.%(ext)s")
    
    def ydl_progress_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            try:
                p = d.get('_percent_str', '0%').replace('%','')
                percent = float(p)
                # Download phase is 0% to 30% of total
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
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise RuntimeError(f"Yuklab olishda xatolik: {e}")
    
    # Yuklab olingan faylni topish
    for f in os.listdir(output_dir):
        if f.startswith("raw_audio"):
            filepath = os.path.join(output_dir, f)
            file_size = os.path.getsize(filepath) / (1024 * 1024)
            print(f"   ✅ Yuklab olindi: {f} ({file_size:.1f} MB)")
            return filepath
    
    raise FileNotFoundError("Yuklab olingan fayl topilmadi")


def get_audio_duration(filepath: str) -> float:
    """Audio davomiyligini olish (xotirani ishlatmasdan)"""
    info = sf.info(filepath)
    return info.duration


def load_audio_chunk(filepath: str, start_sec: float, duration_sec: float, sr: int) -> np.ndarray:
    """
    Audio fayldan faqat kerakli bo'lakni yuklash.
    Butun faylni xotiraga yuklamasdan ishlaydi.
    """
    info = sf.info(filepath)
    file_sr = info.samplerate
    
    start_frame = int(start_sec * file_sr)
    num_frames = int(duration_sec * file_sr)
    
    # Fayl chegarasidan chiqmaslik
    total_frames = info.frames
    if start_frame >= total_frames:
        return np.array([], dtype=np.float32)
    if start_frame + num_frames > total_frames:
        num_frames = total_frames - start_frame
    
    # Faqat kerakli qismini o'qish
    audio, file_sr = sf.read(filepath, start=start_frame, frames=num_frames, dtype='float32')
    
    # Stereo bo'lsa mono qilish
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    
    # Namuna tezligini o'zgartirish (agar kerak bo'lsa)
    if file_sr != sr:
        audio = librosa.resample(audio, orig_sr=file_sr, target_sr=sr)
    
    return audio.astype(np.float32)


def load_audio(filepath: str) -> tuple:
    """Audio faylni yuklash va mono qilish (qisqa fayllar uchun)"""
    print("\n📂 Audio fayl yuklanmoqda...")
    
    audio, sr = librosa.load(filepath, sr=SAMPLE_RATE, mono=True)
    duration = len(audio) / sr
    
    print(f"   ✅ Davomiyligi: {format_time(duration)}")
    print(f"   ✅ Namuna tezligi: {sr} Hz")
    
    return audio, sr


def apply_bandpass_filter(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    Nutq chastotasi oralig'idan tashqari shovqinlarni kesish.
    80 Hz dan past va 12 kHz dan yuqori chastotalarni olib tashlaydi.
    """
    # Yuqori o'tkazgich (past shovqinlarni kesish)
    sos_high = butter(5, HIGHPASS_FREQ, btype='highpass', fs=sr, output='sos')
    audio = sosfilt(sos_high, audio)
    
    # Past o'tkazgich (yuqori shovqinlarni kesish)
    sos_low = butter(5, LOWPASS_FREQ, btype='lowpass', fs=sr, output='sos')
    audio = sosfilt(sos_low, audio)
    
    return audio.astype(np.float32)


def reduce_noise(audio: np.ndarray, sr: int, strength: float) -> np.ndarray:
    """
    Orqa fon shovqinini kamaytirish.
    Spectral gating usulidan foydalanadi.
    """
    # Shovqinni kamaytirish
    reduced = nr.reduce_noise(
        y=audio,
        sr=sr,
        stationary=True,         # Statsionar shovqin uchun (RAM xavfsiz va tezroq)
        prop_decrease=strength,  # Kamaytirish kuchi
        n_fft=2048,
        hop_length=512
    )
    
    return reduced


def enhance_voice(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    Nutq ovozini kuchaytirish.
    Nutq chastotalari oralig'ini biroz oshiradi.
    """
    # STFT orqali chastota domeniga o'tish
    stft = librosa.stft(audio, n_fft=2048, hop_length=512)
    magnitude = np.abs(stft)
    phase = np.angle(stft)
    
    # Chastota o'qi
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    
    # Nutq chastotalarini kuchaytirish (300 Hz - 3000 Hz)
    voice_boost = np.ones_like(freqs)
    for i, f in enumerate(freqs):
        if 200 <= f <= 400:
            # Past nutq chastotalarini biroz kuchaytirish
            voice_boost[i] = 1.3
        elif 400 <= f <= 3000:
            # Asosiy nutq oralig'i
            voice_boost[i] = 1.5
        elif 3000 <= f <= 5000:
            # Tiniqlik uchun
            voice_boost[i] = 1.2
    
    # Kuchaytirishni qo'llash
    magnitude = magnitude * voice_boost[:, np.newaxis]
    
    # Qaytadan audio signalga o'tish
    stft_enhanced = magnitude * np.exp(1j * phase)
    enhanced = librosa.istft(stft_enhanced, hop_length=512)
    
    # Uzunligini moslashtirish
    if len(enhanced) > len(audio):
        enhanced = enhanced[:len(audio)]
    elif len(enhanced) < len(audio):
        enhanced = np.pad(enhanced, (0, len(audio) - len(enhanced)))
    
    return enhanced


def normalize_loudness(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    Ovoz balandligini LUFS standartiga moslashtirish.
    Podcast va video uchun -16 LUFS standart hisoblanadi.
    """
    meter = pyln.Meter(sr)
    
    # Joriy balandlikni o'lchash
    current_loudness = meter.integrated_loudness(audio)
    
    if np.isinf(current_loudness):
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio * (0.9 / peak)
        return audio
    
    # LUFS normalizatsiya
    normalized = pyln.normalize.loudness(audio, current_loudness, TARGET_LOUDNESS)
    
    # Clipping oldini olish
    peak = np.max(np.abs(normalized))
    if peak > 0.99:
        normalized = normalized * (0.99 / peak)
    
    return normalized


def apply_limiter(audio: np.ndarray, threshold: float = 0.95) -> np.ndarray:
    """
    Oddiy limiter — cho'qqi qiymatlarning oldini olish.
    Audio sifatini saqlagan holda balandlikni cheklaydi.
    """
    peak = np.max(np.abs(audio))
    if peak > threshold:
        audio = audio * (threshold / peak)
    
    return audio


def crossfade(chunk_a: np.ndarray, chunk_b: np.ndarray, fade_samples: int) -> np.ndarray:
    """
    Ikki bo'lakni silliq ulash (crossfade).
    Bo'laklar orasidagi keskin o'tishlarni yo'qotadi.
    """
    if fade_samples <= 0 or len(chunk_a) == 0 or len(chunk_b) == 0:
        return np.concatenate([chunk_a, chunk_b])
    
    # Fade uzunligini moslashtirish
    fade_samples = min(fade_samples, len(chunk_a), len(chunk_b))
    
    # Fade out (birinchi bo'lakning oxiri)
    fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
    # Fade in (ikkinchi bo'lakning boshi)
    fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    
    # Birinchi bo'lakdan overlap qismini ajratish
    result = np.copy(chunk_a)
    result[-fade_samples:] = result[-fade_samples:] * fade_out + chunk_b[:fade_samples] * fade_in
    
    # Ikkinchi bo'lakning qolgan qismini qo'shish
    result = np.concatenate([result, chunk_b[fade_samples:]])
    
    return result


def process_chunk(audio: np.ndarray, sr: int, noise_strength: float) -> np.ndarray:
    """Bitta bo'lakni to'liq tozalash"""
    # 1. Chastota filtri
    audio = apply_bandpass_filter(audio, sr)
    
    # 2. Shovqin kamaytirish
    audio = reduce_noise(audio, sr, noise_strength)
    
    # 3. Nutq kuchaytirish
    audio = enhance_voice(audio, sr)
    
    return audio


def process_long_video(raw_path: str, sr: int, noise_strength: float, progress_callback=None) -> np.ndarray:
    """
    Uzun videolarni bo'laklab (chunk) qayta ishlash.
    Har bir bo'lak alohida tozalanadi, diskka saqlanadi va keyin birlashtiriladi.
    Bu VPS xotirasini (RAM) tejaydi.
    """
    total_duration = get_audio_duration(raw_path)
    chunk_duration = CHUNK_DURATION_SEC
    overlap = OVERLAP_SEC
    overlap_samples = int(overlap * sr)
    
    # Bo'laklar sonini hisoblash
    step = chunk_duration - overlap
    num_chunks = max(1, int(np.ceil((total_duration - overlap) / step)))
    
    logging.info(f"Long video processing started: {num_chunks} chunks, total {total_duration:.1f}s")
    print(f"\n📐 Bo'laklab qayta ishlash rejasi:")
    print(f"   📏 Umumiy davomiylik: {format_time(total_duration)}")
    print(f"   🧩 Bo'lak hajmi: {format_time(chunk_duration)}")
    print(f"   🔢 Bo'laklar soni: {num_chunks}")
    print(f"   🔗 Overlap: {overlap} soniya")
    
    chunk_files = []
    start_time = time.time()
    
    try:
        for i in range(num_chunks):
            chunk_start = i * step
            chunk_len = min(chunk_duration, total_duration - chunk_start)
            
            if chunk_len <= 0:
                break
            
            # Progress reporting BEFORE starting chunk
            progress_pct = (i / num_chunks) * 100
            if progress_callback:
                current_total_progress = 30 + (progress_pct * 0.6)
                # Ensure we move past 30% immediately
                if i == 0: current_total_progress = 31
                progress_callback(current_total_progress)

            logging.info(f"Processing chunk {i+1}/{num_chunks} ({format_time(chunk_start)})")
            
            # Bo'lakni yuklash
            chunk = load_audio_chunk(raw_path, chunk_start, chunk_len, sr)
            if len(chunk) == 0:
                continue
            
            # Bo'lakni tozalash
            processed = process_chunk(chunk, sr, noise_strength)
            del chunk
            
            # Diskka vaqtinchalik saqlash (RAMni tejash uchun)
            temp_chunk_path = f"{raw_path}_chunk_{i}.wav"
            sf.write(temp_chunk_path, processed, sr, subtype='PCM_16')
            chunk_files.append(temp_chunk_path)
            del processed
            
            logging.info(f"Chunk {i+1}/{num_chunks} saved to disk")
            print(f"   └─ ✅ Bo'lak {i+1} tayyor")

        # Barcha bo'laklarni birlashtirish
        logging.info("Merging chunks from disk...")
        result_audio = np.array([], dtype=np.float32)
        
        for idx, cf in enumerate(chunk_files):
            processed, _ = sf.read(cf, dtype='float32')
            if len(result_audio) == 0:
                result_audio = processed
            else:
                result_audio = crossfade(result_audio, processed, overlap_samples)
            
            # Merge progress (90-95%)
            if progress_callback:
                merge_progress = 90 + (idx / len(chunk_files) * 5)
                progress_callback(merge_progress)
            
            os.remove(cf) # Faylni o'chirish

        total_time = time.time() - start_time
        logging.info(f"Processing finished in {total_time:.1f}s")
        return result_audio

    except Exception as e:
        logging.error(f"Error in process_long_video: {e}")
        # Clean up temp files on error
        for cf in chunk_files:
            if os.path.exists(cf): os.remove(cf)
        raise e

def save_audio(audio: np.ndarray, sr: int, output_path: str, fmt: str = "mp3"):
    """Audio faylni saqlash"""
    logging.info(f"Saving final audio to {output_path} (Format: {fmt})")
    print(f"\n💾 Fayl saqlanmoqda: {output_path}")
    
    # Avval WAV sifatida saqlash
    temp_wav = output_path + ".temp.wav"
    sf.write(temp_wav, audio, sr, subtype='PCM_16')
    
    if fmt == "wav":
        shutil.move(temp_wav, output_path)
    else:
        # FFmpeg orqali konvertatsiya
        cmd = [
            "ffmpeg", "-y",
            "-i", temp_wav,
            "-codec:a", "libmp3lame" if fmt == "mp3" else "aac",
            "-b:a", "192k",
            "-ar", str(sr),
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            os.remove(temp_wav)
        except subprocess.CalledProcessError:
            # Agar konvertatsiya muvaffaqiyatsiz bo'lsa, WAV sifatida saqlash
            shutil.move(temp_wav, output_path.rsplit('.', 1)[0] + '.wav')
            output_path = output_path.rsplit('.', 1)[0] + '.wav'
            print("   ⚠️ MP3 konvertatsiya muvaffaqiyatsiz, WAV sifatida saqlandi")
    
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"   ✅ Saqlandi! Hajmi: {file_size:.1f} MB")
    
    return output_path


def get_video_title(url: str) -> str:
    """YouTube video sarlavhasini olish"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--get-title", "--no-playlist", url],
            capture_output=True, text=True, timeout=15
        )
        title = result.stdout.strip()
        # Fayl nomi uchun tozalash
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
        return safe_title[:80] if safe_title else "cleaned_audio"
    except Exception:
        return "cleaned_audio"


def process_video(url: str, output_path: str = None, fmt: str = "mp3",
                  noise_strength: float = NOISE_REDUCE_STRENGTH, progress_callback=None):
    """
    Asosiy jarayon — YouTube videoni yuklab olib, tozalash.
    Uzun videolar avtomatik ravishda bo'laklab qayta ishlanadi.
    """
    print("=" * 60)
    print("🎬 YouTube Audio Cleaner")
    print("=" * 60)
    print(f"🔗 URL: {url}")
    
    total_start = time.time()
    
    # FFmpeg tekshirish
    check_ffmpeg()
    
    # Video sarlavhasini olish
    video_title = get_video_title(url)
    print(f"📹 Video: {video_title}")
    
    # Chiqish fayl nomi
    if output_path is None:
        output_path = f"{video_title}_cleaned.{fmt}"
    
    # Vaqtinchalik papka
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. YouTube'dan audio yuklab olish
        raw_path = download_audio(url, tmpdir, progress_callback)
        
        # Audio davomiyligini tekshirish
        duration = get_audio_duration(raw_path)
        print(f"\n⏱️  Audio davomiyligi: {format_time(duration)}")
        
        if duration > LONG_VIDEO_THRESHOLD:
            # ═══ UZUN VIDEO — bo'laklab ishlash ═══
            print(f"\n📢 Uzun video aniqlandi! Bo'laklab qayta ishlash ishlatiladi.")
            print(f"   (Oddiy rejim: <{format_time(LONG_VIDEO_THRESHOLD)}, "
                  f"bo'laklab rejim: >{format_time(LONG_VIDEO_THRESHOLD)})")
            
            # Bo'laklab tozalash
            audio = process_long_video(raw_path, SAMPLE_RATE, noise_strength, progress_callback)
            sr = SAMPLE_RATE
            
            # Umumiy normalizatsiya va limiter
            print(f"\n📊 Umumiy ovoz normallashtirilmoqda...")
            audio = normalize_loudness(audio, sr)
            audio = apply_limiter(audio)
            if progress_callback: progress_callback(90)
            
        else:
            # ═══ QISQA VIDEO — oddiy rejim ═══
            print(f"\n📢 Qisqa video — oddiy rejimda ishlanadi.")
            
            # 2. Audio yuklash
            audio, sr = load_audio(raw_path)
            
            # 3. Chastota filtri
            print("\n🔧 Chastota filtri qo'llanmoqda...")
            audio = apply_bandpass_filter(audio, sr)
            if progress_callback: progress_callback(40)
            print(f"   ✅ Oraliq: {HIGHPASS_FREQ} Hz — {LOWPASS_FREQ} Hz")
            
            # 4. Shovqin kamaytirish
            print(f"\n🔇 Shovqin kamaytirilmoqda (kuch: {noise_strength:.0%})...")
            audio = reduce_noise(audio, sr, noise_strength)
            if progress_callback: progress_callback(60)
            print("   ✅ Shovqin kamaytirildi")
            
            # 5. Nutq kuchaytirish
            print("\n🎤 Nutq tozalanmoqda...")
            audio = enhance_voice(audio, sr)
            if progress_callback: progress_callback(80)
            print("   ✅ Nutq kuchaytirildi")
            
            # 6. Ovoz balandligini normallashtirish
            print(f"\n📊 Ovoz balandligi normallashtirilmoqda (maqsad: {TARGET_LOUDNESS} LUFS)...")
            audio = normalize_loudness(audio, sr)
            if progress_callback: progress_callback(90)
            meter = pyln.Meter(sr)
            new_loudness = meter.integrated_loudness(audio)
            if not np.isinf(new_loudness):
                print(f"   ✅ Yangi balandlik: {new_loudness:.1f} LUFS")
            
            # 7. Limiter
            print("\n🛑 Limiter qo'llanmoqda...")
            audio = apply_limiter(audio)
            print(f"   ✅ Cho'qqi qiymati: {np.max(np.abs(audio)):.3f}")
        
        # 8. Saqlash
        final_path = save_audio(audio, sr, output_path, fmt)
        if progress_callback: progress_callback(100)
    
    total_elapsed = time.time() - total_start
    
    print("\n" + "=" * 60)
    print(f"🎉 Tayyor! Tozalangan fayl: {final_path}")
    print(f"⏱️  Umumiy vaqt: {format_time(total_elapsed)}")
    print("=" * 60)
    
    return final_path


def main():
    global CHUNK_DURATION_SEC
    parser = argparse.ArgumentParser(
        description="YouTube videolardan ovozni yuklab olib, shovqinni olib tashlash va normallash",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Misollar:
  python clean_audio.py "https://youtube.com/watch?v=VIDEO_ID"
  python clean_audio.py "https://youtu.be/VIDEO_ID" --output nutq.mp3
  python clean_audio.py "URL" --format wav --noise-reduce-strength 0.8
  python clean_audio.py "URL" --noise-reduce-strength 0.9  (kuchli tozalash)
  python clean_audio.py "URL" --noise-reduce-strength 0.3  (yengil tozalash)
  python clean_audio.py "URL" --chunk-size 180  (3 daqiqalik bo'laklar)
        """
    )
    
    parser.add_argument("url", help="YouTube video havolasi")
    parser.add_argument(
        "--output", "-o",
        help="Chiqish fayl nomi (masalan: tozalangan.mp3)",
        default=None
    )
    parser.add_argument(
        "--format", "-f",
        help="Chiqish formati (mp3, wav, aac)",
        choices=["mp3", "wav", "aac"],
        default="mp3"
    )
    parser.add_argument(
        "--noise-reduce-strength", "-n",
        help="Shovqin kamaytirish kuchi (0.0 - 1.0, standart: 0.6)",
        type=float,
        default=NOISE_REDUCE_STRENGTH
    )
    parser.add_argument(
        "--chunk-size",
        help="Bo'lak hajmi soniyalarda (uzun videolar uchun, standart: 300)",
        type=int,
        default=CHUNK_DURATION_SEC
    )
    
    args = parser.parse_args()
    
    # Kuchni tekshirish
    if not 0.0 <= args.noise_reduce_strength <= 1.0:
        print("❌ Shovqin kamaytirish kuchi 0.0 dan 1.0 gacha bo'lishi kerak")
        sys.exit(1)
    
    # Chunk size ni yangilash
    CHUNK_DURATION_SEC = args.chunk_size
    
    try:
        process_video(
            url=args.url,
            output_path=args.output,
            fmt=args.format,
            noise_strength=args.noise_reduce_strength
        )
    except Exception as e:
        print(f"\n❌ Xatolik yuz berdi: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
