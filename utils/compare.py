import os
import difflib
from docx import Document

def extract_text(filepath: str) -> str:
    """Extracts text from a given document."""
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    if ext == '.docx':
        try:
            doc = Document(filepath)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except Exception as e:
            raise Exception(f"Failed to read Word document: {e}")
    elif ext in ['.txt', '.md']:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            raise Exception(f"Failed to read text file: {e}")
    else:
        raise Exception(f"Unsupported file format for comparison: {ext}")
    return text

def compare_documents(file1_path: str, file2_path: str, output_html_path: str) -> bool:
    """Compares two documents and generates an HTML diff file."""
    try:
        text1 = extract_text(file1_path)
        text2 = extract_text(file2_path)
        
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        differ = difflib.HtmlDiff()
        
        html_diff = differ.make_file(
            lines1, lines2, 
            fromdesc=f"Original File", 
            todesc=f"Modified File",
            context=False,
            numlines=2
        )
        
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_diff)
            
        return True
    except Exception as e:
        print(f"Comparison error: {e}")
        return False
