import os
import zipfile
import tempfile
import rarfile
import logging

def rar_to_zip(rar_path: str, output_zip_path: str, progress_callback=None) -> bool:
    """
    Extracts a RAR file and compresses its contents into a ZIP file.
    Returns True if successful, False otherwise.
    """
    try:
        logging.info(f"Starting RAR to ZIP conversion: {rar_path}")
        if progress_callback: progress_callback(10)
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Extract RAR
            logging.info("Extracting RAR content to temp directory")
            if progress_callback: progress_callback(20)
            with rarfile.RarFile(rar_path) as rf:
                rf.extractall(path=temp_dir)
            
            if progress_callback: progress_callback(50)
            
            # Count files for progress
            all_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    all_files.append(os.path.join(root, file))
            
            total_files = len(all_files)
            logging.info(f"Compression started: {total_files} files found")
            
            # 2. Compress to ZIP
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for idx, file_path in enumerate(all_files):
                    # Create a relative path for the zip file
                    arcname = os.path.relpath(file_path, start=temp_dir)
                    zf.write(file_path, arcname)
                    
                    if progress_callback and total_files > 0:
                        # Zip phase is 50% to 100%
                        current_progress = 50 + ((idx + 1) / total_files * 50)
                        progress_callback(current_progress)
            logging.info("ZIP compression finished successfully")
        return True
    except Exception as e:
        logging.error(f"Error converting RAR to ZIP: {e}")
        return False
