import sys
sys.path.append('c:\\Users\\5\\.gemini\\antigravity\\scratch\\UtilityBot')
from utils.converter import md_to_pdf

md_path = r"C:\Users\5\.gemini\antigravity\brain\958d02d4-37b9-40d3-9e3f-5b00d73d5ebd\artifacts\optimal_security_topology.md"
out_path = r"C:\Users\5\.gemini\antigravity\scratch\UtilityBot\test_out.pdf"

try:
    print("Starting conversion...")
    success = md_to_pdf(md_path, out_path)
    print(f"Success: {success}")
except Exception as e:
    import traceback
    traceback.print_exc()
