from PIL import Image
import os
import logging

def compress_image(input_image_path: str, output_image_path: str, quality: int = 60, progress_callback=None) -> bool:
    """
    Compresses an image file and saves it to output_image_path.
    质量 (quality) parameter reduces file size (default 60).
    """
    try:
        if progress_callback: progress_callback(20)
        with Image.open(input_image_path) as img:
            if progress_callback: progress_callback(40)
            # Convert to RGB if image is in RGBA mode (like some PNGs)
            # because saving as JPEG requires RGB.
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            if progress_callback: progress_callback(60)
            img.save(output_image_path, "JPEG", optimize=True, quality=quality)
        
        if progress_callback: progress_callback(100)
        return os.path.exists(output_image_path)
    except Exception as e:
        logging.error(f"Error compressing image: {e}")
        return False
