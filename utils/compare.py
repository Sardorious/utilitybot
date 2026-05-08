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
    # Custom CSS moved inside function to potentially help with IDE linter noise
    css_styles = """
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style type="text/css">
    :root {
        --bg-main: #0f172a;
        --bg-table: #1e293b;
        --bg-header: #334155;
        --border: #475569;
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
        --accent: #38bdf8;
        --add-bg: rgba(16, 185, 129, 0.15);
        --add-text: #6ee7b7;
        --add-hl: rgba(16, 185, 129, 0.4);
        --sub-bg: rgba(239, 68, 68, 0.15);
        --sub-text: #fca5a5;
        --sub-hl: rgba(239, 68, 68, 0.4);
        --chg-bg: rgba(245, 158, 11, 0.15);
        --chg-text: #fde68a;
        --chg-hl: rgba(245, 158, 11, 0.4);
    }
    body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 2rem; line-height: 1.5; }
    h1 { text-align: center; font-weight: 700; font-size: 28px; margin-bottom: 2rem; color: var(--accent); text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .diff_container { max-width: 98%; margin: 0 auto; }
    table.diff { width: 100%; background: var(--bg-table); border-radius: 12px; border-collapse: collapse; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3); font-size: 15px; overflow: visible; }
    table.diff thead { background-color: var(--bg-header); }
    table.diff th { font-weight: 600; padding: 18px; text-align: center; color: #fff; border-bottom: 2px solid var(--border); }
    table.diff td { padding: 10px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: top; white-space: pre-wrap !important; word-break: break-word !important; overflow-wrap: anywhere !important; }
    table.diff td.diff_header { background-color: rgba(0,0,0,0.2); color: var(--text-muted); text-align: center; width: 60px; border-right: 1px solid var(--border); user-select: none; font-family: 'Fira Code', monospace; font-size: 13px; }
    .diff_add { background-color: var(--add-bg); color: var(--add-text); }
    .diff_sub { background-color: var(--sub-bg); color: var(--sub-text); }
    .diff_chg { background-color: var(--chg-bg); color: var(--chg-text); }
    span.diff_add { background-color: var(--add-hl); color: #fff; font-weight: 600; border-radius: 3px; padding: 0 3px; border-bottom: 2px solid #10b981; }
    span.diff_sub { background-color: var(--sub-hl); color: #fff; text-decoration: line-through; font-weight: 600; border-radius: 3px; padding: 0 3px; border-bottom: 2px solid #ef4444; }
    span.diff_chg { background-color: var(--chg-hl); color: #fff; font-weight: 600; border-radius: 3px; padding: 0 3px; border-bottom: 2px solid #f59e0b; }
    a { color: var(--accent); text-decoration: none; }
    </style>
    """
    
    try:
        text1 = extract_text(file1_path)
        text2 = extract_text(file2_path)
        
        # Avoid issues with completely empty texts
        if not text1.strip() and not text2.strip():
            text1 = "--- Bo'sh hujjat ---"
            text2 = "--- Bo'sh hujjat ---"
        
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        differ = difflib.HtmlDiff()
        # Set custom styles
        differ._styles = css_styles
        
        html_diff = differ.make_file(
            lines1, lines2, 
            fromdesc="📝 Original Hujjat", 
            todesc="✏️ O'zgartirilgan Hujjat",
            context=True,
            numlines=0
        )
        
        # Remove the default legend table if it exists
        html_diff = html_diff.replace('<table class="diff" summary="Legends">', '<table class="diff" style="display:none" summary="Legends">')
        
        # Inject title and container
        html_diff = html_diff.replace('<body>', '<body><div class="diff_container"><h1>📑 Hujjatlar o\'rtasidagi farqlar</h1>')
        html_diff = html_diff.replace('</body>', '</div></body>')
        
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_diff)
            
        return True
    except Exception as e:
        print(f"Comparison error: {e}")
        return False
