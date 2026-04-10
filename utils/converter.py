import os

import sys
import subprocess

def word_to_pdf(docx_path: str, output_pdf_path: str) -> bool:
    """
    Converts a Word (.docx) file to a PDF file.
    On Windows it uses docx2pdf (requires MS Word).
    On Linux it uses LibreOffice CLI (requires libreoffice to be installed).
    """
    try:
        if sys.platform == "win32":
            from docx2pdf import convert
            convert(docx_path, output_pdf_path)
            return os.path.exists(output_pdf_path)
        else:
            outdir = os.path.dirname(output_pdf_path)
            cmd = ['libreoffice', '--headless', '--convert-to', 'pdf', docx_path, '--outdir', outdir]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            base_name = os.path.splitext(os.path.basename(docx_path))[0]
            generated_pdf = os.path.join(outdir, f"{base_name}.pdf")
            
            if generated_pdf != output_pdf_path and os.path.exists(generated_pdf):
                os.rename(generated_pdf, output_pdf_path)
                
            return os.path.exists(output_pdf_path)
    except Exception as e:
        print(f"Error converting Word to PDF: {e}")
        return False

def pdf_to_word(pdf_path: str, output_docx_path: str) -> bool:
    """
    Converts a PDF file to a Word (.docx) file using OCR.
    Extracts text to plain string and saves it handling UTF-8.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        from docx import Document
        import os

        doc = Document()
        pdf_document = fitz.open(pdf_path)
        
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap()
            
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            text = pytesseract.image_to_string(img, lang='uzb+rus+eng+tur')
            if text.strip():
                doc.add_paragraph(text.strip())
            
            if page_num < len(pdf_document) - 1:
                doc.add_page_break()
                
        doc.save(output_docx_path)
        pdf_document.close()
        return os.path.exists(output_docx_path)
    except Exception as e:
        print(f"Error converting PDF to Word with OCR: {e}")
        return False

def md_to_pdf(md_path: str, output_pdf_path: str) -> bool:
    """
    Converts a Markdown (.md) file to a PDF file.
    """
    try:
        import markdown
        from xhtml2pdf import pisa
        
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            
        html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite', 'tables'])
        
        css = """
        <style>
            @page { margin: 2cm; }
            body { font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; }
            h1, h2, h3, h4, h5, h6 { color: #222; margin-top: 1.5em; margin-bottom: 0.5em; }
            code { font-family: "Courier New", Courier, monospace; background-color: #f8f9fa; padding: 2px 4px; border-radius: 4px; font-size: 0.9em; }
            pre { background-color: #f8f9fa; padding: 12px; border-radius: 4px; white-space: pre-wrap; font-family: "Courier New", Courier, monospace; font-size: 0.9em; border: 1px solid #e9ecef; }
            blockquote { border-left: 4px solid #adb5bd; padding-left: 15px; color: #6c757d; font-style: italic; margin-left: 0; }
            table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
            th, td { border: 1px solid #dee2e6; padding: 8px; text-align: left; }
            th { background-color: #e9ecef; font-weight: bold; }
            a { color: #0d6efd; text-decoration: none; }
            img { max-width: 100%; height: auto; }
            hr { border: 0; border-top: 1px solid #eee; margin: 20px 0; }
        </style>
        """
        full_html = f"<html><head>{css}</head><body>{html_content}</body></html>"
        
        with open(output_pdf_path, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(full_html, dest=result_file)
            
        return not pisa_status.err
    except Exception as e:
        import logging
        import traceback
        logging.getLogger().error(f"Error in md_to_pdf: {e}\n{traceback.format_exc()}")
        try:
            with open("errors.log", "a", encoding="utf-8") as f:
                f.write(f"MD2PDF ERR: {e}\n{traceback.format_exc()}\n")
        except:
            pass
        print(f"Error converting Markdown to PDF: {e}")
        return False
