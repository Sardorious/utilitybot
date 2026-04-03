from PIL import Image
import os

def compress_image(input_image_path: str, output_image_path: str, quality: int = 60) -> bool:
    """
    Compresses an image file and saves it to output_image_path.
    质量 (quality) parameter reduces file size (default 60).
    """
    try:
        with Image.open(input_image_path) as img:
            # Convert to RGB if image is in RGBA mode (like some PNGs)
            # because saving as JPEG requires RGB.
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            img.save(output_image_path, "JPEG", optimize=True, quality=quality)
        return os.path.exists(output_image_path)
    except Exception as e:
        print(f"Error compressing image: {e}")
        return False
