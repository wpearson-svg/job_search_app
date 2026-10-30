"""Reads the master resume (.docx, .txt or .md) into plain text."""
import html
import os
import re
import zipfile


def read_resume(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        lines = []
        for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
            text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.S))
            text = html.unescape(text).strip()
            if text:
                lines.append(text)
        return "\n".join(lines)
    with open(path, encoding="utf-8") as f:
        return f.read()
