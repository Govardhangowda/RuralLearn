import json, logging, sqlite3
from pathlib import Path
from PySide6.QtCore import QStandardPaths
from .content import CURRICULUM, SUBJECTS, QUIZZES, EXPLORE

log = logging.getLogger('rurallearn')

class Database:
    def __init__(self, path=None):
        base = Path(path) if path else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        if path is None:
            base.mkdir(parents=True, exist_ok=True); base = base / 'rurallearn.sqlite3'
        else:
            base.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(base)
        self.conn = sqlite3.connect(self.path); self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.initialize()
    def initialize(self):
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS subjects(name TEXT PRIMARY KEY, icon TEXT);
        CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, subject TEXT, chapter TEXT, title TEXT, body TEXT, example TEXT, concepts TEXT, summary TEXT, questions TEXT, UNIQUE(subject,chapter,title));
        CREATE TABLE IF NOT EXISTS completions(lesson_id INTEGER PRIMARY KEY, completed_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(lesson_id) REFERENCES lessons(id));
        CREATE TABLE IF NOT EXISTS quiz_questions(id INTEGER PRIMARY KEY,subject TEXT,chapter TEXT,lesson TEXT,prompt TEXT,options TEXT,answer INTEGER,explanation TEXT,topic TEXT);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, subject TEXT,chapter TEXT,score INTEGER,total INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attempt_answers(id INTEGER PRIMARY KEY,attempt_id INTEGER,question_id INTEGER,selected INTEGER,correct INTEGER,FOREIGN KEY(attempt_id) REFERENCES attempts(id));
        CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY,message TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS imported(id INTEGER PRIMARY KEY,name TEXT,subject TEXT,chapter TEXT,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY,title TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,chat_id INTEGER,role TEXT,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(chat_id) REFERENCES chats(id));
        ''')
        count = self.conn.execute('SELECT COUNT(*) FROM lessons').fetchone()[0]
        if not count:
            for subject in SUBJECTS:
                self.conn.execute('INSERT OR IGNORE INTO subjects(name,icon) VALUES(?,?)',(subject, {'Physics':'◈','Chemistry':'⚗','Mathematics':'∑','Biology':'✿','English':'Aa','Kannada':'ಕ'}[subject]))
            for subject, chapters in CURRICULUM.items():
                for chapter, lessons in chapters.items():
                    for title,body,example,concepts,summary,questions in lessons:
                        self.conn.execute('INSERT INTO lessons(subject,chapter,title,body,example,concepts,summary,questions) VALUES(?,?,?,?,?,?,?,?)',(subject,chapter,title,body,example,json.dumps(concepts,ensure_ascii=False),summary,json.dumps(questions,ensure_ascii=False)))
            for row in QUIZZES:
                subject,chapter,lesson,prompt,options,answer,explanation,topic=row
                self.conn.execute('INSERT INTO quiz_questions(subject,chapter,lesson,prompt,options,answer,explanation,topic) VALUES(?,?,?,?,?,?,?,?)',(subject,chapter,lesson,prompt,json.dumps(options,ensure_ascii=False),answer,explanation,topic))
            self.conn.commit()
        for key,value in [('student_name','Learner'),('ai_demo','1'),('model',''),('language','Simple explanations')]:
            self.conn.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(key,value))
        self.conn.commit()
        # Older versions stored imported files only in `imported`; expose them in
        # the normal lesson catalogue too, without changing the database schema.
        self.sync_imported_lessons()
    def sync_imported_lessons(self):
        for item in self.all('SELECT id,name,subject,chapter,body FROM imported ORDER BY id'):
            title=f"[Imported #{item['id']}] {item['name']}"
            self.conn.execute('''INSERT OR IGNORE INTO lessons
                (subject,chapter,title,body,example,concepts,summary,questions)
                VALUES(?,?,?,?,?,?,?,?)''',(
                item['subject'],item['chapter'],title,item['body'],
                f"Content imported locally from {item['name']}.",
                json.dumps(['Imported local material','Use the source text to review this topic'],ensure_ascii=False),
                item['body'][:500],json.dumps([],ensure_ascii=False)))
        self.conn.commit()
    def all(self,sql,args=()): return self.conn.execute(sql,args).fetchall()
    def one(self,sql,args=()): return self.conn.execute(sql,args).fetchone()
    def run(self,sql,args=()):
        cur=self.conn.execute(sql,args); self.conn.commit(); return cur
    def setting(self,key,default=''): 
        row=self.one('SELECT value FROM settings WHERE key=?',(key,)); return row['value'] if row else default
    def set_setting(self,key,value): self.run('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))
    def log_activity(self,message): self.run('INSERT INTO activity(message) VALUES(?)',(message,))
    def lessons(self,subject=None,chapter=None):
        sql='SELECT l.*,c.completed_at FROM lessons l LEFT JOIN completions c ON c.lesson_id=l.id WHERE 1=1'; args=[]
        if subject: sql+=' AND l.subject=?'; args.append(subject)
        if chapter: sql+=' AND l.chapter=?'; args.append(chapter)
        return self.all(sql+' ORDER BY l.id',args)
    def search(self,query,subject=None,limit=4):
        terms=[w.lower() for w in query.split() if len(w)>2]
        rows=self.all('SELECT subject,chapter,title,body,example,summary FROM lessons')+self.all('SELECT subject,chapter,name AS title,body,body AS example,body AS summary FROM imported')
        ranked=[]
        for r in rows:
            if subject and r['subject']!=subject: continue
            text=' '.join(str(r[k] or '') for k in ('subject','chapter','title','body','example','summary')).lower()
            score=sum(text.count(w) for w in terms)
            if score: ranked.append((score,r))
        ranked.sort(key=lambda x:x[0],reverse=True)
        return [r for _,r in ranked[:limit]]
    def reset_progress(self):
        self.conn.executescript('DELETE FROM completions; DELETE FROM attempts; DELETE FROM attempt_answers; DELETE FROM activity; DELETE FROM messages; DELETE FROM chats;'); self.conn.commit()
    def close(self): self.conn.close()
