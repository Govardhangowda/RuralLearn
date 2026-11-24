from pathlib import Path
from .db import Database

def import_textbook(db: Database, path: str, subject='General', chapter='Imported'):
    p=Path(path); suffix=p.suffix.lower()
    if suffix=='.txt': text=p.read_text(encoding='utf-8',errors='replace')
    elif suffix=='.pdf':
        try:
            from pypdf import PdfReader
            text='\n'.join(page.extract_text() or '' for page in PdfReader(str(p)).pages)
        except Exception as exc: raise RuntimeError(f'Could not read PDF: {exc}')
    else: raise ValueError('Choose a .txt or .pdf file.')
    if not text.strip(): raise ValueError('No readable text was found in that file.')
    cur=db.run('INSERT INTO imported(name,subject,chapter,body) VALUES(?,?,?,?)',(p.name,subject,chapter,text))
    db.sync_imported_lessons()
    return cur.lastrowid

def format_sources(rows):
    return '\n'.join(f"[{r['subject']} · {r['chapter']} · {r['title']}] {r['body'][:1000]}" for r in rows)
