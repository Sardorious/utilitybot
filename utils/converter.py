import os
import logging
import traceback
import sys
import subprocess
import shutil

def word_to_pdf(docx_path: str, output_pdf_path: str, progress_callback=None) -> bool:
    """
    Converts a Word (.docx) file to a PDF file.
    On Windows it uses docx2pdf (requires MS Word).
    On Linux it uses LibreOffice CLI (requires libreoffice to be installed).
    """
    try:
        logging.info(f"Starting Word to PDF conversion: {docx_path}")
        if progress_callback: progress_callback(20)
        if sys.platform == "win32":
            from docx2pdf import convert
            convert(docx_path, output_pdf_path)
            return os.path.exists(output_pdf_path)
        else:
            outdir = os.path.dirname(output_pdf_path)
            # Use a temporary user profile for LibreOffice to avoid profile locks/hangs in service mode
            profile_dir = os.path.join(outdir, f"lo_profile_{os.getpid()}")
            os.makedirs(profile_dir, exist_ok=True)
            
            cmd = [
                'libreoffice', 
                '--headless', 
                f'-env:UserInstallation=file://{profile_dir}', 
                '--convert-to', 'pdf', 
                docx_path, 
                '--outdir', outdir
            ]
            
            logging.info(f"Running LibreOffice with Profile: {profile_dir}")
            if progress_callback: progress_callback(40)
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if progress_callback: progress_callback(80)
            
            # Clean up temp profile
            try: shutil.rmtree(profile_dir)
            except: pass
            
            base_name = os.path.splitext(os.path.basename(docx_path))[0]
            generated_pdf = os.path.join(outdir, f"{base_name}.pdf")
            
            if generated_pdf != output_pdf_path and os.path.exists(generated_pdf):
                os.rename(generated_pdf, output_pdf_path)
            
            if progress_callback: progress_callback(100)
            return os.path.exists(output_pdf_path)
    except Exception as e:
        logging.error(f"Error converting Word to PDF: {e}")
        return False

def pdf_to_word(pdf_path: str, output_docx_path: str, progress_callback=None) -> bool:
    """
    Converts a PDF file to a Word (.docx) file using OCR.
    Extracts text to plain string and saves it handling UTF-8.
    """
    try:
        logging.info(f"Starting PDF to Word (OCR) conversion: {pdf_path}")
        if progress_callback: progress_callback(10)
        import fitz
        import pytesseract
        from PIL import Image
        from docx import Document
        import os

        doc = Document()
        pdf_document = fitz.open(pdf_path)
        total_pages = len(pdf_document)
        logging.info(f"PDF loaded: {total_pages} pages found")
        
        for page_num in range(total_pages):
            logging.info(f"Processing page {page_num + 1}/{total_pages}")
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap()
            
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            text = pytesseract.image_to_string(img, lang='uzb+rus+eng+tur')
            if text.strip():
                doc.add_paragraph(text.strip())
            
            if page_num < total_pages - 1:
                doc.add_page_break()
            
            if progress_callback and total_pages > 0:
                current_percent = 10 + ((page_num + 1) / total_pages * 80)
                progress_callback(current_percent)
                
        doc.save(output_docx_path)
        pdf_document.close()
        if progress_callback: progress_callback(100)
        return os.path.exists(output_docx_path)
    except Exception as e:
        logging.error(f"Error converting PDF to Word with OCR: {e}")
        return False

def md_to_pdf(md_path: str, output_pdf_path: str, progress_callback=None) -> bool:
    """
    Converts a Markdown (.md) file to a PDF file.
    """
    try:
        logging.info(f"Starting Markdown to PDF conversion: {md_path}")
        if progress_callback: progress_callback(10)
        import markdown
        from xhtml2pdf import pisa
        import os
        
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            
        import base64, zlib, re
        def replacer(match):
            mermaid_code = match.group(1).strip()
            compressed = zlib.compress(mermaid_code.encode('utf-8'), 9)
            b64 = base64.urlsafe_b64encode(compressed).decode('ascii')
            return f"![Mermaid Diagram](https://kroki.io/mermaid/png/{b64})"
            
        md_content = re.sub(r'```mermaid\s*\n(.*?)\n```', replacer, md_content, flags=re.DOTALL | re.IGNORECASE)
        if progress_callback: progress_callback(40)
            
        html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite', 'tables'])
        if progress_callback: progress_callback(60)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_dir = os.path.join(script_dir, "fonts")
        font_path = os.path.join(font_dir, "Roboto-Regular.ttf").replace('\\', '/')
        
        if not os.path.exists(font_path):
            import urllib.request
            os.makedirs(font_dir, exist_ok=True)
            font_url = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf"
            urllib.request.urlretrieve(font_url, font_path)
        
        css = f"""
        <style>
            @font-face {{
                font-family: 'Roboto';
                src: url('{font_path}');
            }}
            @page {{ margin: 2cm; }}
            body {{ font-family: 'Roboto', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; }}
            h1, h2, h3, h4, h5, h6 {{ font-family: 'Roboto'; color: #222; margin-top: 1.5em; margin-bottom: 0.5em; }}
            code {{ font-family: 'Roboto', monospace; background-color: #f8f9fa; padding: 2px 4px; border-radius: 4px; font-size: 0.9em; }}
            pre {{ background-color: #f8f9fa; padding: 12px; border-radius: 4px; white-space: pre-wrap; font-family: 'Roboto', monospace; font-size: 0.9em; border: 1px solid #e9ecef; }}
            blockquote {{ font-family: 'Roboto'; border-left: 4px solid #adb5bd; padding-left: 15px; color: #6c757d; font-style: italic; margin-left: 0; }}
            table {{ font-family: 'Roboto'; border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ font-family: 'Roboto'; border: 1px solid #dee2e6; padding: 8px; text-align: left; }}
            th {{ background-color: #e9ecef; font-weight: bold; }}
            a {{ color: #0d6efd; text-decoration: none; }}
            img {{ max-width: 100%; height: auto; }}
            hr {{ border: 0; border-top: 1px solid #eee; margin: 20px 0; }}
        </style>
        """
        full_html = f"<html><head>{css}</head><body>{html_content}</body></html>"
        
        with open(output_pdf_path, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(full_html, dest=result_file)
        
        if progress_callback: progress_callback(100)
        return not pisa_status.err
    except Exception as e:
        logging.error(f"Error in md_to_pdf: {e}\n{traceback.format_exc()}")
        return False
