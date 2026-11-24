import json, logging, random
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import *
from .content import SUBJECTS, EXPLORE
from .ai import status as ollama_status, AIWorker, demo_reply
from .retrieval import import_textbook, format_sources

log=logging.getLogger('rurallearn')
STYLE='''
QWidget { background:#f6f4ec; color:#233b39; font-family:"Segoe UI"; font-size:14px; }
QFrame#sidebar { background:#173f3b; border:0; }
QLabel#brand { color:#f7f2e4; font-size:24px; font-weight:800; }
QLabel#muted { color:#74817b; }
QFrame#sidebar QLabel#muted { color:#a9c8bc; letter-spacing:1px; }
QLabel#heroTitle {font-size:28px;font-weight:750;color:#173f3b;}
QLabel#sectionTitle {font-size:20px;font-weight:700;color:#173f3b;}
QFrame#card { background:#fffefa; border:1px solid #e5e8df; border-radius:14px; }
QPushButton { background:#23776a; color:white; border:0; border-radius:9px; padding:10px 15px; font-weight:650; min-height:20px; }
QPushButton:hover { background:#195e55; }
QPushButton:disabled { background:#aebbb3;color:#f5f5f0; }
QPushButton#nav { text-align:left; background:transparent; color:#d7e5dc; padding:12px 15px; border-radius:9px; }
QPushButton#nav:hover,QPushButton#nav[active="true"] { background:#2a5951; color:white; }
QPushButton#secondary { background:#e8efea; color:#235449; }
QLineEdit,QTextEdit,QComboBox { background:white; border:1px solid #dce3db; border-radius:8px; padding:9px; selection-background-color:#23776a; }
QLineEdit:focus,QTextEdit:focus,QComboBox:focus { border:1px solid #4c9c87; }
QProgressBar { background:#e9eee8; border:0; border-radius:5px; height:10px; text-align:center; }
QProgressBar::chunk { background:#e89359; border-radius:5px; }
QListWidget { background:#fffefa; border:1px solid #e8e5db; border-radius:12px; padding:6px; }
QListWidget::item { padding:9px; border-radius:7px; }
QListWidget::item:selected { background:#e3efe8; color:#173f3b; }
QRadioButton { padding:8px; }
QScrollArea { background:transparent; }
QScrollBar:vertical { background:transparent; width:10px; margin:4px 1px; }
QScrollBar::handle:vertical { background:#cbd7ce; border-radius:5px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#9fb7a8; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
'''

def label(text,style=None):
    w=QLabel(text); w.setWordWrap(True)
    if style: w.setObjectName(style)
    return w
def card(layout=None):
    f=QFrame(); f.setObjectName('card')
    if layout:
        l=QVBoxLayout(f); l.setContentsMargins(18,16,18,16); l.setSpacing(10)
    return f
def clear_layout(layout):
    while layout.count():
        item=layout.takeAt(0); w=item.widget()
        if w: w.deleteLater()

def clear_practice_layout(layout):
    """Remove nested Practice controls immediately, then dispose them safely."""
    while layout.count():
        item=layout.takeAt(0)
        widget=item.widget()
        child_layout=item.layout()
        if widget:
            # deleteLater() alone leaves the old widget paintable until Qt's
            # next deferred-delete pass, which caused the quiz/results overlap.
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout:
            clear_practice_layout(child_layout)
            child_layout.deleteLater()

class MainWindow(QMainWindow):
    PAGES=['Dashboard','Learn','AI Tutor','Practice','My Progress','Explore','Settings']
    def __init__(self,db):
        super().__init__(); self.db=db; self.subject='Physics'; self.lesson_id=None; self.quiz_rows=[]; self.quiz_index=0; self.quiz_answers={}; self.chat_id=None; self.ai_thread=None; self.ai_worker=None; self.ai_online=False; self.models=[]
        self.setWindowTitle('RuralLearn'); self.resize(1420,900); self.setMinimumSize(1120,720); self.setStyleSheet(STYLE)
        root=QWidget(); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(238); sl=QVBoxLayout(side); sl.setContentsMargins(18,22,18,18); sl.setSpacing(7)
        brand=label('◈ RuralLearn'); brand.setObjectName('brand'); sl.addWidget(brand); sl.addWidget(label('LEARN AT YOUR PACE','muted'))
        self.nav={}
        for name in self.PAGES:
            b=QPushButton(name); b.setObjectName('nav'); b.clicked.connect(lambda checked=False,n=name:self.go(n)); self.nav[name]=b; sl.addWidget(b)
        sl.addStretch(); sl.addWidget(label('OFFLINE READY','muted')); self.sidebar_status=label('● Local content available'); self.sidebar_status.setStyleSheet('color:#a9d8b1'); sl.addWidget(self.sidebar_status)
        outer.addWidget(side)
        main=QWidget(); ml=QVBoxLayout(main); ml.setContentsMargins(28,18,28,24); ml.setSpacing(14)
        top=QHBoxLayout(); self.breadcrumb=label('Dashboard','muted'); top.addWidget(self.breadcrumb); top.addStretch(); self.ai_badge=label('● AI checking…'); top.addWidget(self.ai_badge); ml.addLayout(top)
        self.stack=QStackedWidget(); ml.addWidget(self.stack,1); outer.addWidget(main,1); self.setCentralWidget(root)
        self.pages={}
        for name in self.PAGES:
            w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(16)
            scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(w); self.stack.addWidget(scroll); self.pages[name]=(scroll,l)
        self.go('Dashboard'); self.refresh_ai(); QTimer.singleShot(100,self.refresh_dashboard)
    def go(self,name):
        self.breadcrumb.setText(name); self.stack.setCurrentWidget(self.pages[name][0])
        for n,b in self.nav.items(): b.setProperty('active',n==name); b.style().unpolish(b); b.style().polish(b)
        {'Dashboard':self.dashboard,'Learn':self.learn,'AI Tutor':self.tutor,'Practice':self.practice,'My Progress':self.progress,'Explore':self.explore,'Settings':self.settings}[name]()
    def title(self,layout,text,sub=None):
        layout.addWidget(label(text,'heroTitle'))
        if sub: layout.addWidget(label(sub,'muted'))
    def button(self,text,fn,secondary=False):
        b=QPushButton(text)
        if secondary:b.setObjectName('secondary')
        b.clicked.connect(fn);return b
    def card_label(self,title,body):
        f=card(); l=QVBoxLayout(f); l.setContentsMargins(18,16,18,16);l.addWidget(label(title,'sectionTitle'));l.addWidget(body);return f
    def completions(self): return self.db.one('SELECT COUNT(*) n FROM completions')['n']
    def dashboard(self):
        _,l=self.pages['Dashboard']; clear_layout(l)
        done=self.completions(); total=len(self.db.lessons()); quizzes=self.db.one('SELECT COUNT(*) n FROM attempts')['n']; avg=self.db.one('SELECT AVG(100.0*score/total) n FROM attempts')['n']
        self.title(l,f"Welcome back, {self.db.setting('student_name','Learner')} 👋",'Small steps add up. Pick up where you left off.')
        hero=card(); hl=QHBoxLayout(hero);hl.setContentsMargins(24,20,24,20);col=QVBoxLayout(); col.addWidget(label('Your learning journey','sectionTitle')); col.addWidget(label(f'{done} of {total} lessons completed · {quizzes} quiz attempts · '+(f'{avg:.0f}% quiz average' if avg is not None else 'No quiz scores yet'),'muted'));pb=QProgressBar();pb.setValue(round(done/total*100) if total else 0);col.addWidget(pb);hl.addLayout(col,1)
        row=QHBoxLayout();row.addWidget(self.button('Continue learning →',self.continue_learning));row.addWidget(self.button('Ask the AI tutor',lambda:self.go('AI Tutor'),True));hl.addLayout(row);l.addWidget(hero)
        l.addWidget(label('Choose a subject','sectionTitle'))
        grid=QGridLayout();grid.setSpacing(12)
        icons={'Physics':'◈','Chemistry':'⚗','Mathematics':'∑','Biology':'✿','English':'Aa','Kannada':'ಕ'}
        for i,s in enumerate(SUBJECTS):
            lessons=self.db.lessons(s); finished=sum(bool(x['completed_at']) for x in lessons); percent=round(finished/len(lessons)*100) if lessons else 0
            f=card();fl=QVBoxLayout(f);fl.setContentsMargins(16,14,16,14);fl.addWidget(label(f"{icons[s]}   {s}",'sectionTitle'));fl.addWidget(label(f'{finished}/{len(lessons)} lessons · {percent}%','muted'));p=QProgressBar();p.setValue(percent);fl.addWidget(p);b=self.button('Open subject →',lambda checked=False,x=s:self.open_subject(x),True);fl.addWidget(b);grid.addWidget(f,i//3,i%3)
        l.addLayout(grid)
        rec=self.recommendations()
        rbox=card();rl=QVBoxLayout(rbox);rl.setContentsMargins(18,14,18,14);rl.addWidget(label('Recommended for you','sectionTitle'))
        if rec:
            for item in rec[:2]:
                roww=QHBoxLayout();roww.addWidget(label(f"{item['title']} · {item['reason']}"));roww.addWidget(self.button('Open →',lambda checked=False,r=item:self.open_recommendation(r)));rl.addLayout(roww)
        else: rl.addWidget(label('Start a lesson and take a quiz to get recommendations based on your learning.','muted'))
        l.addWidget(rbox)
        activity=self.db.all('SELECT message,created_at FROM activity ORDER BY id DESC LIMIT 4'); af=card();al=QVBoxLayout(af);al.setContentsMargins(18,14,18,14);al.addWidget(label('Recent activity','sectionTitle'))
        for a in activity: al.addWidget(label('•  '+a['message']+'   ·   '+a['created_at'][:16],'muted'))
        if not activity:al.addWidget(label('Your learning activity will appear here.','muted'))
        l.addWidget(af)
        service=QHBoxLayout()
        for text in ['● Offline lessons available','● SQLite database ready',('● Ollama connected' if self.ai_online else '● AI demo mode · Ollama unavailable')]:
            tag=label(text,'muted');tag.setStyleSheet('background:#e8efea;border-radius:9px;padding:10px;color:#315f50');service.addWidget(tag)
        l.addLayout(service);l.addStretch()
    def continue_learning(self):
        row=self.db.one('SELECT l.id,l.subject FROM lessons l LEFT JOIN completions c ON c.lesson_id=l.id WHERE c.lesson_id IS NULL ORDER BY l.id LIMIT 1')
        if row:self.open_lesson(row['id'])
        else:self.go('Learn')
    def open_subject(self,s):self.subject=s;self.go('Learn')
    def learn(self):
        _,l=self.pages['Learn'];clear_layout(l);self.title(l,'Learn','Browse locally available sample lessons. Content is educational sample material, not an official textbook.')
        controls=QHBoxLayout();self.subject_box=QComboBox();self.subject_box.addItems(SUBJECTS);self.subject_box.setCurrentText(self.subject);self.subject_box.currentTextChanged.connect(self.select_subject);controls.addWidget(label('Subject:'));controls.addWidget(self.subject_box);controls.addStretch();l.addLayout(controls)
        body=QHBoxLayout(); self.chapter_list=QListWidget();self.lesson_list=QListWidget();self.chapter_list.setMaximumWidth(270);self.lesson_list.setMaximumWidth(380);body.addWidget(self.chapter_list);body.addWidget(self.lesson_list);self.lesson_view=QWidget();self.lesson_layout=QVBoxLayout(self.lesson_view);self.lesson_layout.setAlignment(Qt.AlignTop);body.addWidget(self.lesson_view,1);l.addLayout(body,1)
        self.chapter_list.currentTextChanged.connect(self.populate_lessons);self.lesson_list.currentRowChanged.connect(self.show_selected_lesson);self.populate_chapters()
        if self.lesson_id:
            idx=self.lesson_list.findData(self.lesson_id)
            if idx>=0:self.lesson_list.setCurrentRow(idx)
    def select_subject(self,s):self.subject=s;self.populate_chapters()
    def populate_chapters(self):
        if not hasattr(self,'chapter_list'):return
        self.chapter_list.clear(); rows=self.db.all('SELECT chapter FROM lessons WHERE subject=? GROUP BY chapter ORDER BY MIN(id)',(self.subject,))
        for r in rows:self.chapter_list.addItem(r['chapter'])
        if self.chapter_list.count():self.chapter_list.setCurrentRow(0)
    def populate_lessons(self,chapter):
        if not hasattr(self,'lesson_list'):return
        self.lesson_list.clear()
        for r in self.db.lessons(self.subject,chapter):
            item=QListWidgetItem(('✓  ' if r['completed_at'] else '○  ')+r['title']);item.setData(Qt.UserRole,r['id']);self.lesson_list.addItem(item)
        if self.lesson_list.count():self.lesson_list.setCurrentRow(0)
    def show_selected_lesson(self,row):
        clear_layout(self.lesson_layout)
        if row<0:return
        item=self.lesson_list.item(row); lesson=self.db.one('SELECT * FROM lessons WHERE id=?',(item.data(Qt.UserRole),))
        if not lesson:return
        self.lesson_id=lesson['id']; self.current_lesson=lesson
        self.lesson_layout.addWidget(label(lesson['title'],'heroTitle'));self.lesson_layout.addWidget(label(f"{lesson['subject']}  /  {lesson['chapter']} · Sample learning content",'muted'))
        self.lesson_layout.addWidget(label('Learning objectives','sectionTitle'));self.lesson_layout.addWidget(label('By the end, you should be able to explain the main idea and apply it to a familiar example.'))
        self.lesson_layout.addWidget(label('Explanation','sectionTitle'));self.lesson_layout.addWidget(label(lesson['body']))
        self.lesson_layout.addWidget(label('Example','sectionTitle'));self.lesson_layout.addWidget(label(lesson['example']))
        self.lesson_layout.addWidget(label('Key concepts','sectionTitle'))
        for c in json.loads(lesson['concepts']):self.lesson_layout.addWidget(label('•  '+c))
        self.lesson_layout.addWidget(label('Summary','sectionTitle'));self.lesson_layout.addWidget(label(lesson['summary']))
        self.lesson_layout.addWidget(label('Check your understanding','sectionTitle'))
        for q in json.loads(lesson['questions']):self.lesson_layout.addWidget(label('•  '+q))
        buttons=QHBoxLayout();buttons.addWidget(self.button('← Previous',lambda:self.step_lesson(-1),True));buttons.addWidget(self.button('Mark complete ✓',lambda:self.complete_lesson(lesson['id'])));buttons.addWidget(self.button('Next →',lambda:self.step_lesson(1),True));buttons.addWidget(self.button('Practice this topic',lambda:self.start_quiz(lesson['subject'],lesson['chapter'])));self.lesson_layout.addLayout(buttons)
    def open_lesson(self,lid):
        self.lesson_id=lid; row=self.db.one('SELECT subject,chapter FROM lessons WHERE id=?',(lid,))
        if not row:return
        self.subject=row['subject'];self.go('Learn');self.subject_box.setCurrentText(self.subject);self.chapter_list.setCurrentRow(max(0,self.chapter_list.findItems(row['chapter'],Qt.MatchExactly)[0].row()));idx=self.lesson_list.findData(lid)
        if idx>=0:self.lesson_list.setCurrentRow(idx)
    def step_lesson(self,step):
        row=self.lesson_list.currentRow()+step
        if 0<=row<self.lesson_list.count():self.lesson_list.setCurrentRow(row)
    def complete_lesson(self,lid):
        self.db.run('INSERT OR IGNORE INTO completions(lesson_id) VALUES(?)',(lid,));self.db.log_activity('Completed '+self.current_lesson['title']);self.populate_lessons(self.chapter_list.currentItem().text());self.refresh_dashboard()
        QMessageBox.information(self,'Lesson complete','Progress saved on this device.')
    def recommendations(self):
        result=[]
        for a in self.db.all('SELECT * FROM attempts ORDER BY id DESC'):
            score=100*a['score']/a['total'] if a['total'] else 0
            answers=self.db.all('SELECT q.topic,q.lesson,q.subject,q.chapter,aa.correct FROM attempt_answers aa JOIN quiz_questions q ON q.id=aa.question_id WHERE aa.attempt_id=?',(a['id'],))
            wrong=[x for x in answers if not x['correct']]
            if score<50 and wrong:
                x=wrong[0];reason=f"Your last {x['topic']} quiz score was {score:.0f}%; review the foundations."
                lesson=self.db.one('SELECT id,title FROM lessons WHERE subject=? AND chapter=? ORDER BY id LIMIT 1',(x['subject'],x['chapter']))
                if lesson:result.append({'title':lesson['title'],'reason':reason,'lesson_id':lesson['id']})
            elif score<70 and wrong:
                x=wrong[0];reason=f"You scored {score:.0f}%; a little more practice can strengthen this topic."
                result.append({'title':x['topic']+' practice','reason':reason,'subject':x['subject'],'chapter':x['chapter']})
            elif score>=70:
                nextl=self.db.one('SELECT id,title FROM lessons WHERE subject=? AND id>(SELECT COALESCE(MAX(id),0) FROM lessons WHERE chapter=?) ORDER BY id LIMIT 1',(a['subject'],a['chapter']))
                if nextl:result.append({'title':nextl['title'],'reason':f'You scored {score:.0f}%—you are ready to progress.','lesson_id':nextl['id']})
            if result:break
        return result
    def open_recommendation(self,r):
        if r.get('lesson_id'):self.open_lesson(r['lesson_id'])
        elif r.get('subject'):self.start_quiz(r['subject'],r['chapter'])

    def start_quiz(self,subject=None,chapter=None):
        if subject:self.subject=subject
        self.quiz_subject=self.subject;self.quiz_chapter=chapter or ''
        self.quiz_rows=self.db.all('SELECT * FROM quiz_questions WHERE subject=? '+('AND chapter=? ' if self.quiz_chapter else '')+'ORDER BY id',((self.quiz_subject,self.quiz_chapter) if self.quiz_chapter else (self.quiz_subject,)))
        if not self.quiz_rows:
            QMessageBox.information(self,'Practice','No questions are available for this selection yet.');return
        self.quiz_index=0;self.quiz_answers={};self.go('Practice');self.render_question()
    def practice(self):
        _,l=self.pages['Practice'];clear_practice_layout(l);self.title(l,'Practice','Choose a subject or focus on a topic, then check your answers with clear explanations.')
        controls=QHBoxLayout();self.practice_subject=QComboBox();self.practice_subject.addItems(SUBJECTS);self.practice_subject.setCurrentText(self.subject);self.practice_topic=QComboBox();self.practice_topic.addItem('All topics');
        for r in self.db.all('SELECT DISTINCT chapter FROM quiz_questions WHERE subject=?',(self.practice_subject.currentText(),)):self.practice_topic.addItem(r['chapter'])
        self.practice_subject.currentTextChanged.connect(lambda s:self.update_practice_topics());controls.addWidget(label('Subject'));controls.addWidget(self.practice_subject);controls.addWidget(label('Topic'));controls.addWidget(self.practice_topic);controls.addWidget(self.button('Start practice →',self.start_practice));l.addLayout(controls)
        self.practice_content=QVBoxLayout();self.practice_content.setSpacing(14);l.addLayout(self.practice_content)
        overview=QHBoxLayout(); overview.setSpacing(14)
        weak=self.db.all('SELECT q.subject,q.chapter,q.topic,COUNT(*) n FROM attempt_answers aa JOIN quiz_questions q ON q.id=aa.question_id WHERE aa.correct=0 GROUP BY q.subject,q.chapter,q.topic ORDER BY n DESC LIMIT 3')
        weak_card=card();wl=QVBoxLayout(weak_card);wl.setContentsMargins(18,16,18,16);wl.addWidget(label('Topics to strengthen','sectionTitle'))
        if weak:
            for item in weak:
                line=QHBoxLayout();line.addWidget(label(f"{item['topic']} · {item['n']} missed"));line.addWidget(self.button('Practice',lambda checked=False,x=item:self.start_quiz(x['subject'],x['chapter']),True));wl.addLayout(line)
        else: wl.addWidget(label('Your missed answers will suggest focused practice here.','muted'))
        overview.addWidget(weak_card,1)
        recent=self.db.one('SELECT subject,chapter,score,total,created_at FROM attempts ORDER BY id DESC LIMIT 1')
        recent_card=card();rl=QVBoxLayout(recent_card);rl.setContentsMargins(18,16,18,16);rl.addWidget(label('Latest attempt','sectionTitle'))
        if recent:
            rl.addWidget(label(f"{recent['subject']} · {recent['chapter'] or 'Mixed topics'}"));rl.addWidget(label(f"{recent['score']} / {recent['total']} correct",'heroTitle'));rl.addWidget(label(recent['created_at'][:16],'muted'))
        else: rl.addWidget(label('Take a quiz to start building your practice history.','muted'))
        overview.addWidget(recent_card,1);self.practice_content.addLayout(overview)
        tip=card();tl=QHBoxLayout(tip);tl.setContentsMargins(18,14,18,14);tl.addWidget(label('Practice tip','sectionTitle'));tl.addWidget(label('Try a short topic quiz, review each explanation, then retake it to see what has improved.'));self.practice_content.addWidget(tip)
        l.addStretch(1)
    def update_practice_topics(self):
        if not hasattr(self,'practice_topic'):return
        self.practice_topic.clear();self.practice_topic.addItem('All topics')
        for r in self.db.all('SELECT DISTINCT chapter FROM quiz_questions WHERE subject=?',(self.practice_subject.currentText(),)):self.practice_topic.addItem(r['chapter'])
    def start_practice(self):self.start_quiz(self.practice_subject.currentText(),None if self.practice_topic.currentText()=='All topics' else self.practice_topic.currentText())
    def render_question(self):
        _,l=self.pages['Practice'];clear_practice_layout(l)
        if not self.quiz_rows:return
        q=self.quiz_rows[self.quiz_index];self.title(l,'Practice · '+q['chapter'],f'Question {self.quiz_index+1} of {len(self.quiz_rows)} · Answers are checked when you submit.')
        f=card();fl=QVBoxLayout(f);fl.setContentsMargins(22,20,22,20);fl.addWidget(label(q['prompt'],'sectionTitle'));self.option_group=QButtonGroup(self);self.option_buttons=[]
        for i,opt in enumerate(json.loads(q['options'])):
            rb=QRadioButton(opt);self.option_group.addButton(rb,i);self.option_buttons.append(rb);fl.addWidget(rb)
            if self.quiz_answers.get(self.quiz_index)==i:rb.setChecked(True)
        l.addStretch(1);l.addWidget(f);row=QHBoxLayout();row.addWidget(self.button('← Previous',lambda:self.move_question(-1),True));row.addWidget(self.button('Next →',lambda:self.move_question(1),True));row.addStretch();row.addWidget(self.button('Submit quiz ✓',self.submit_quiz));l.addLayout(row);l.addStretch(1)
    def move_question(self,delta):
        checked=self.option_group.checkedId()
        if checked>=0:self.quiz_answers[self.quiz_index]=checked
        target=self.quiz_index+delta
        if 0<=target<len(self.quiz_rows):self.quiz_index=target;self.render_question()
    def submit_quiz(self):
        checked=self.option_group.checkedId()
        if checked>=0:self.quiz_answers[self.quiz_index]=checked
        if len(self.quiz_answers)<len(self.quiz_rows):
            if QMessageBox.question(self,'Submit quiz','Some questions are unanswered. Submit anyway?')!=QMessageBox.Yes:return
        score=sum(self.quiz_answers.get(i,-1)==q['answer'] for i,q in enumerate(self.quiz_rows));cur=self.db.run('INSERT INTO attempts(subject,chapter,score,total) VALUES(?,?,?,?)',(self.quiz_subject,self.quiz_chapter,score,len(self.quiz_rows)));aid=cur.lastrowid
        for i,q in enumerate(self.quiz_rows):self.db.run('INSERT INTO attempt_answers(attempt_id,question_id,selected,correct) VALUES(?,?,?,?)',(aid,q['id'],self.quiz_answers.get(i,-1),int(self.quiz_answers.get(i,-1)==q['answer'])))
        self.db.log_activity(f"Quiz: {self.quiz_subject} · {score}/{len(self.quiz_rows)} correct");self.show_results(aid,score)
    def show_results(self,aid,score):
        _,l=self.pages['Practice'];clear_practice_layout(l);total=len(self.quiz_rows);self.title(l,'Quiz results',f'{score} out of {total} correct · {round(100*score/total)}%')
        for i,q in enumerate(self.quiz_rows):
            selected=self.quiz_answers.get(i,-1);correct=selected==q['answer'];opts=json.loads(q['options']);f=card();fl=QVBoxLayout(f);fl.setContentsMargins(16,12,16,12);fl.addWidget(label(('✓ Correct  ' if correct else '↻ Review  ')+q['prompt'],'sectionTitle'));fl.addWidget(label('Your answer: '+(opts[selected] if selected>=0 else 'Not answered')));fl.addWidget(label('Correct answer: '+opts[q['answer']]));fl.addWidget(label(q['explanation'],'muted'));l.addWidget(f)
        actions=QHBoxLayout();actions.addWidget(self.button('Retake quiz ↻',lambda:self.start_quiz(self.quiz_subject,self.quiz_chapter)));actions.addWidget(self.button('View progress',lambda:self.go('My Progress'),True));actions.addWidget(self.button('Dashboard',lambda:self.go('Dashboard'),True));l.addLayout(actions);l.addStretch();self.refresh_dashboard()

    def refresh_ai(self):
        self.ai_online,self.models=ollama_status()
        if self.ai_online and self.models:
            self.ai_badge.setText('● Ollama connected');self.ai_badge.setStyleSheet('color:#267559;font-weight:700');self.sidebar_status.setText('● Offline content · Ollama ready')
        elif self.ai_online:
            self.ai_badge.setText('● Ollama online · no models installed');self.ai_badge.setStyleSheet('color:#b36e35;font-weight:700');self.sidebar_status.setText('● Local content · AI demo mode')
        else:
            self.ai_badge.setText('● Demo tutor · Ollama unavailable');self.ai_badge.setStyleSheet('color:#b36e35;font-weight:700');self.sidebar_status.setText('● Local content · AI demo mode')
    def tutor(self):
        _,l=self.pages['AI Tutor'];clear_layout(l);self.title(l,'AI Tutor','Ask for a simple explanation, a worked example, or help with a lesson.')
        bar=QHBoxLayout();self.model_box=QComboBox();self.model_box.setMinimumWidth(190)
        if self.models:self.model_box.addItems(self.models)
        else:self.model_box.addItem('Ollama model unavailable')
        saved=self.db.setting('model','');idx=self.model_box.findText(saved)
        if idx>=0:self.model_box.setCurrentIndex(idx)
        self.context_subject=QComboBox();self.context_subject.addItem('Any subject');self.context_subject.addItems(SUBJECTS);self.context_subject.setCurrentText(self.subject if self.subject in SUBJECTS else 'Any subject')
        self.context_input=QLineEdit();self.context_input.setPlaceholderText('Optional chapter or topic (e.g. Atoms)');self.context_input.setText(self.current_lesson['chapter'] if hasattr(self,'current_lesson') else '')
        bar.addWidget(label('Model'));bar.addWidget(self.model_box);bar.addWidget(label('Subject'));bar.addWidget(self.context_subject);bar.addWidget(self.context_input);bar.addWidget(self.button('＋ New chat',self.new_chat,True));l.addLayout(bar)
        self.chat_history=QTextBrowser();self.chat_history.setOpenExternalLinks(False);l.addWidget(self.chat_history,1)
        prompts=QHBoxLayout()
        for p in ['Explain atoms in simple words','Give me a step-by-step example','What does my lesson say about this?']:
            prompts.addWidget(self.button(p,lambda checked=False,x=p:self.send_prompt(x),True))
        l.addLayout(prompts);entry=QHBoxLayout();self.chat_input=QLineEdit();self.chat_input.setPlaceholderText('Ask your tutor…');self.chat_input.returnPressed.connect(self.send_chat);entry.addWidget(self.chat_input,1);self.send_button=self.button('Send →',self.send_chat);entry.addWidget(self.send_button);l.addLayout(entry)
        self.ensure_chat();self.render_chat()
    def ensure_chat(self):
        if not self.chat_id:
            cur=self.db.run('INSERT INTO chats(title) VALUES(?)',('Learning chat',));self.chat_id=cur.lastrowid
    def new_chat(self):self.chat_id=None;self.ensure_chat();self.render_chat()
    def render_chat(self):
        if not hasattr(self,'chat_history'):return
        rows=self.db.all('SELECT role,body FROM messages WHERE chat_id=? ORDER BY id',(self.chat_id,));html=[]
        if not rows:html.append('<p style="color:#72817b">Try a suggested question, or ask about any subject. Your chat stays on this device.</p>')
        for m in rows:
            color='#dff0e6' if m['role']=='assistant' else '#fff0db';who='Tutor' if m['role']=='assistant' else 'You';body=m['body'].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br>');html.append(f'<div style="background:{color};padding:12px;margin:8px;border-radius:10px"><b>{who}</b><br>{body}</div>')
        self.chat_history.setHtml(''.join(html))
    def send_prompt(self,text):self.chat_input.setText(text);self.send_chat()
    def send_chat(self):
        text=self.chat_input.text().strip()
        if not text:return
        self.ensure_chat();self.db.run('INSERT INTO messages(chat_id,role,body) VALUES(?,?,?)',(self.chat_id,'user',text));self.chat_input.clear();self.render_chat();self.send_button.setEnabled(False);self.send_button.setText('Thinking…')
        context_rows=self.db.search(text,None if self.context_subject.currentText()=='Any subject' else self.context_subject.currentText())
        if self.context_input.text().strip():
            additional=self.db.all('SELECT subject,chapter,title,body,example,summary FROM lessons WHERE chapter LIKE ? OR title LIKE ?',('%'+self.context_input.text()+'%','%'+self.context_input.text()+'%'));context_rows=additional[:4] or context_rows
        context=format_sources(context_rows)
        self.ai_source_refs=[f"{r['subject']} · {r['chapter']} · {r['title']}" for r in context_rows]
        if self.ai_online and self.models:
            model=self.model_box.currentText();self.db.set_setting('model',model);history=[{'role':r['role'],'content':r['body']} for r in self.db.all('SELECT role,body FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 12',(self.chat_id,))[::-1]]
            self.ai_thread=QThread();self.ai_worker=AIWorker(model,history,context,self.db.setting('language','Simple explanations'));self.ai_worker.moveToThread(self.ai_thread);self.ai_thread.started.connect(self.ai_worker.run);self.ai_worker.finished.connect(self.ai_finished);self.ai_worker.failed.connect(self.ai_failed);self.ai_worker.finished.connect(self.ai_thread.quit);self.ai_worker.failed.connect(self.ai_thread.quit);self.ai_thread.start()
        else:
            QTimer.singleShot(450,lambda:self.ai_finished(demo_reply(text,context)))
    def ai_finished(self,text):
        if getattr(self,'ai_source_refs',[]): text+='\n\nSources: '+'; '.join(self.ai_source_refs)
        self.db.run('INSERT INTO messages(chat_id,role,body) VALUES(?,?,?)',(self.chat_id,'assistant',text));self.send_button.setEnabled(True);self.send_button.setText('Send →');self.render_chat()
    def ai_failed(self,error):
        log.error('Ollama request failed: %s',error);self.send_button.setEnabled(True);self.send_button.setText('Send →');self.db.run('INSERT INTO messages(chat_id,role,body) VALUES(?,?,?)',(self.chat_id,'assistant','I could not reach Ollama for that answer. Check that Ollama is running and the selected model is installed. Your lesson library, quizzes, and saved progress remain available offline.'));self.render_chat()

    def progress(self):
        _,l=self.pages['My Progress'];clear_layout(l);self.title(l,'My Progress','A picture of the work you have actually saved on this device.')
        total=len(self.db.lessons());done=self.completions();attempts=self.db.all('SELECT * FROM attempts ORDER BY id DESC');avg=sum(100*a['score']/a['total'] for a in attempts if a['total'])/len(attempts) if attempts else 0
        row=QHBoxLayout()
        for name,value in [('Lessons completed',f'{done}/{total}'),('Quiz attempts',str(len(attempts))),('Average quiz score',f'{avg:.0f}%' if attempts else '—')]:
            f=card();fl=QVBoxLayout(f);fl.setContentsMargins(16,14,16,14);fl.addWidget(label(name,'muted'));fl.addWidget(label(value,'heroTitle'));row.addWidget(f)
        l.addLayout(row);l.addWidget(label('Subject progress','sectionTitle'))
        for s in SUBJECTS:
            rows=self.db.lessons(s);n=sum(bool(x['completed_at']) for x in rows);f=card();fl=QVBoxLayout(f);fl.setContentsMargins(14,10,14,10);fl.addWidget(label(f'{s} · {n}/{len(rows)} lessons'));p=QProgressBar();p.setValue(round(n*100/len(rows)) if rows else 0);fl.addWidget(p);l.addWidget(f)
        scorecard=card();sc=QVBoxLayout(scorecard);sc.setContentsMargins(16,14,16,14);sc.addWidget(label('Quiz history','sectionTitle'))
        for a in attempts[:8]:sc.addWidget(label(f"{a['subject']} · {a['chapter'] or 'Mixed topics'} — {a['score']}/{a['total']} ({round(100*a['score']/a['total'])}%) · {a['created_at'][:16]}",'muted'))
        if not attempts:sc.addWidget(label('Take a practice quiz to see your scores here.','muted'))
        l.addWidget(scorecard)
        incorrect=self.db.all('SELECT q.topic,COUNT(*) n FROM attempt_answers aa JOIN quiz_questions q ON q.id=aa.question_id WHERE aa.correct=0 GROUP BY q.topic ORDER BY n DESC LIMIT 5');strength=self.db.all('SELECT q.topic,COUNT(*) n FROM attempt_answers aa JOIN quiz_questions q ON q.id=aa.question_id WHERE aa.correct=1 GROUP BY q.topic ORDER BY n DESC LIMIT 5')
        perf=QHBoxLayout()
        for title,rows in [('Topics to revisit',incorrect),('Strengths',strength)]:
            f=card();fl=QVBoxLayout(f);fl.setContentsMargins(16,14,16,14);fl.addWidget(label(title,'sectionTitle'))
            for r in rows:fl.addWidget(label(f"{r['topic']} · {r['n']} {'missed' if title.startswith('Topics') else 'correct'} answers"))
            if not rows:fl.addWidget(label('More quiz answers will build this picture.','muted'))
            perf.addWidget(f)
        l.addLayout(perf);l.addStretch()
    def refresh_dashboard(self):
        if self.stack.currentWidget()==self.pages['Dashboard'][0]:self.dashboard()
    def explore(self):
        _,l=self.pages['Explore'];clear_layout(l);self.title(l,'Explore','Short local reads for curious learners. Available without internet.')
        grid=QGridLayout()
        for i,(category,title,body) in enumerate(EXPLORE):
            f=card();fl=QVBoxLayout(f);fl.setContentsMargins(18,16,18,16);fl.addWidget(label(category.upper(),'muted'));fl.addWidget(label(title,'sectionTitle'));fl.addWidget(label(body));grid.addWidget(f,i//2,i%2)
        l.addLayout(grid);l.addStretch()
    def settings(self):
        _,l=self.pages['Settings'];clear_layout(l);self.title(l,'Settings','Personalize your learning and manage local data.')
        f=card();fl=QVBoxLayout(f);fl.setContentsMargins(18,16,18,16);fl.addWidget(label('Learner profile','sectionTitle'));fl.addWidget(label('Name shown on your dashboard'));self.name_edit=QLineEdit(self.db.setting('student_name','Learner'));fl.addWidget(self.name_edit);fl.addWidget(label('Learning preference'));self.pref=QComboBox();self.pref.addItems(['Simple explanations','Step-by-step examples','Short summaries']);self.pref.setCurrentText(self.db.setting('language','Simple explanations'));fl.addWidget(self.pref);fl.addWidget(self.button('Save preferences',self.save_settings));l.addWidget(f)
        statuscard=card();sl=QVBoxLayout(statuscard);sl.setContentsMargins(18,16,18,16);sl.addWidget(label('Local services','sectionTitle'));online,models=ollama_status();sl.addWidget(label('Offline lessons & SQLite: Available'));sl.addWidget(label(('Ollama: Connected' if online else 'Ollama: Not detected')+' · '+(f'{len(models)} model(s) installed' if models else 'No installed model found')));sl.addWidget(label('Database: '+self.db.path,'muted'));sl.addWidget(self.button('Check Ollama again',self.check_ollama,True));l.addWidget(statuscard)
        tf=card();tl=QVBoxLayout(tf);tl.setContentsMargins(18,16,18,16);tl.addWidget(label('Textbook library','sectionTitle'));tl.addWidget(label('Import local TXT or text-based PDF files. Imported passages are stored locally for search.'));self.imports=QListWidget();tl.addWidget(self.imports)
        for r in self.db.all('SELECT name,subject,chapter,created_at FROM imported ORDER BY id DESC'):self.imports.addItem(f"{r['name']} · {r['subject']} / {r['chapter']} · {r['created_at'][:10]}")
        controls=QHBoxLayout();controls.addWidget(self.button('Import TXT / PDF',self.import_file));controls.addWidget(self.button('Remove selected',self.remove_import,True));tl.addLayout(controls);l.addWidget(tf)
        manage=card();ml=QVBoxLayout(manage);ml.setContentsMargins(18,16,18,16);ml.addWidget(label('Data management','sectionTitle'));ml.addWidget(self.button('Clear AI conversations',self.clear_chats,True));ml.addWidget(self.button('Reset demo progress…',self.reset_progress));l.addWidget(manage);l.addStretch()
    def save_settings(self):self.db.set_setting('student_name',self.name_edit.text().strip() or 'Learner');self.db.set_setting('language',self.pref.currentText());self.db.log_activity('Updated learning preferences');QMessageBox.information(self,'Saved','Your preferences are saved locally.');self.refresh_dashboard()
    def check_ollama(self):self.refresh_ai();self.go('Settings');QMessageBox.information(self,'Ollama','Connected with '+str(len(self.models))+' installed model(s).' if self.ai_online else 'Ollama is not available. The clearly labelled tutor demo remains available.')
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Import local textbook','','Text files (*.txt);;PDF files (*.pdf)')
        if not path:return
        subject,ok=QInputDialog.getItem(self,'Organize textbook','Subject',SUBJECTS,0,False)
        if not ok:return
        chapter,ok=QInputDialog.getText(self,'Organize textbook','Chapter or topic')
        if not ok:return
        try:import_textbook(self.db,path,subject,chapter or 'Imported');self.db.log_activity('Imported local material: '+path.replace('\\','/').rsplit('/',1)[-1]);self.go('Settings')
        except Exception as e:QMessageBox.warning(self,'Import failed',str(e))
    def remove_import(self):
        item=self.imports.currentRow()
        if item<0:return
        rows=self.db.all('SELECT id,name,subject,chapter FROM imported ORDER BY id DESC');row=rows[item]
        title=f"[Imported #{row['id']}] {row['name']}"
        lesson=self.db.one('SELECT id FROM lessons WHERE subject=? AND chapter=? AND title=?',(row['subject'],row['chapter'],title))
        self.db.run('DELETE FROM imported WHERE id=?',(row['id'],))
        if lesson:
            self.db.run('DELETE FROM completions WHERE lesson_id=?',(lesson['id'],))
            self.db.run('DELETE FROM lessons WHERE id=?',(lesson['id'],))
        self.go('Settings')
    def clear_chats(self):
        if QMessageBox.question(self,'Clear conversations','Delete all saved AI chats from this device?')==QMessageBox.Yes:
            self.db.conn.executescript('DELETE FROM messages; DELETE FROM chats;');self.db.conn.commit();self.chat_id=None;QMessageBox.information(self,'Cleared','AI conversations deleted.')
    def reset_progress(self):
        if QMessageBox.question(self,'Reset demo progress','Delete lesson completions, quiz attempts, and activity? This cannot be undone.')==QMessageBox.Yes:
            self.db.reset_progress();self.db.log_activity('Demo progress reset');self.go('Dashboard')
    def closeEvent(self,event):
        self.db.close();super().closeEvent(event)
