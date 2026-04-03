import os
import zipfile
import tempfile
import rarfile

def rar_to_zip(rar_path: str, output_zip_path: str) -> bool:
    """
    Extracts a RAR file and compresses its contents into a ZIP file.
    Returns True if successful, False otherwise.
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Extract RAR
            with rarfile.RarFile(rar_path) as rf:
                rf.extractall(path=temp_dir)
            
            # 2. Compress to ZIP
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Create a relative path for the zip file
                        arcname = os.path.relpath(file_path, start=temp_dir)
                        zf.write(file_path, arcname)
        return True
    except Exception as e:
        print(f"Error converting RAR to ZIP: {e}")
        return False
