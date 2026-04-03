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
    Converts a PDF file to a Word (.docx) file.
    """
    try:
        from pdf2docx import Converter
        cv = Converter(pdf_path)
        cv.convert(output_docx_path, start=0, end=None)
        cv.close()
        return os.path.exists(output_docx_path)
    except Exception as e:
        print(f"Error converting PDF to Word: {e}")
        return False
