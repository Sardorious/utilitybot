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

CUSTOM_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style type="text/css">
body { font-family: 'Inter', sans-serif; background-color: #0f172a; color: #f8fafc; margin: 2rem; padding-bottom: 4rem; }
h1 { text-align: center; font-weight: 600; font-size: 26px; margin-bottom: 2rem; color: #38bdf8; text-transform: uppercase; letter-spacing: 1px; }
table.diff { width: 100%; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); border-collapse: collapse; table-layout: fixed; }
table.diff thead { background-color: #334155; border-bottom: 2px solid #475569; }
table.diff th { font-weight: 600; padding: 16px; text-align: center; color: #f1f5f9; font-size: 16px; width: 50%; }
table.diff tbody tr:hover { background-color: rgba(255, 255, 255, 0.02); }
table.diff td { padding: 10px 12px; border-bottom: 1px solid #334155; vertical-align: top; font-family: 'Fira Code', monospace; font-size: 14px; word-wrap: break-word; line-height: 1.5; }
table.diff td.diff_header { background-color: #0f172a; color: #64748b; text-align: center; width: 40px; border-right: 1px solid #334155; user-select: none; font-size: 12px; font-weight: 500; }
table.diff td.diff_add { background-color: rgba(16, 185, 129, 0.05); color: #a7f3d0; }
table.diff td.diff_chg { background-color: rgba(245, 158, 11, 0.05); color: #fde68a; }
table.diff td.diff_sub { background-color: rgba(239, 68, 68, 0.05); color: #fecaca; }
span.diff_add { background-color: rgba(16, 185, 129, 0.3); font-weight: 600; border-radius: 3px; padding: 1px 3px; border: 1px solid rgba(16, 185, 129, 0.5); }
span.diff_sub { background-color: rgba(239, 68, 68, 0.3); text-decoration: line-through; font-weight: 600; border-radius: 3px; padding: 1px 3px; border: 1px solid rgba(239, 68, 68, 0.5); }
span.diff_chg { background-color: rgba(245, 158, 11, 0.3); font-weight: 600; border-radius: 3px; padding: 1px 3px; border: 1px solid rgba(245, 158, 11, 0.5); }
</style>
"""

def compare_documents(file1_path: str, file2_path: str, output_html_path: str) -> bool:
    """Compares two documents and generates an HTML diff file."""
    try:
        text1 = extract_text(file1_path)
        text2 = extract_text(file2_path)
        
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        differ = difflib.HtmlDiff(wrapcolumn=70)
        differ._styles = CUSTOM_CSS
        
        html_diff = differ.make_file(
            lines1, lines2, 
            fromdesc=f"📝 Original Hujjat", 
            todesc=f"✏️ O'zgartirilgan Hujjat",
            context=True,
            numlines=0
        )
        
        html_diff = html_diff.replace('<body>', '<body><h1>📑 Hujjatlar o\'rtasidagi farqlar</h1>')
        
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_diff)
            
        return True
    except Exception as e:
        print(f"Comparison error: {e}")
        return False
