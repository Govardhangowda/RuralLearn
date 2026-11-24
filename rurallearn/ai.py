import json, urllib.request, urllib.error
from PySide6.QtCore import QObject, Signal, QThread
from .retrieval import format_sources

OLLAMA='http://localhost:11434'

def status():
    try:
        with urllib.request.urlopen(OLLAMA+'/api/tags',timeout=1.5) as r: data=json.loads(r.read().decode('utf-8'))
        return True,[m.get('name','') for m in data.get('models',[])]
    except Exception: return False,[]

class AIWorker(QObject):
    finished=Signal(str); failed=Signal(str)
    def __init__(self,model,messages,context,preference='Simple explanations'): super().__init__(); self.model=model; self.messages=messages; self.context=context; self.preference=preference
    def run(self):
        try:
            msgs=[{'role':'system','content':'You are a patient, encouraging tutor for a rural school learner. Use simple language. Teach step by step, use a concrete example, and ask a short check question. Learner preference: '+self.preference+'. Ground textbook claims only in supplied context; if context is missing say so. Context:\n'+(self.context or 'No matching local learning passage was retrieved.') }]+self.messages
            payload=json.dumps({'model':self.model,'messages':msgs,'stream':False}).encode('utf-8')
            req=urllib.request.Request(OLLAMA+'/api/chat',data=payload,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=120) as r: data=json.loads(r.read().decode('utf-8'))
            self.finished.emit(data['message']['content'])
        except Exception as e: self.failed.emit(str(e))

def demo_reply(text,context=''):
    q=text.lower()
    if any(w in q for w in ('atom','atoms')):
        answer='An atom is a tiny building block that makes up all matter. Think of it like one small brick in a huge wall. Atoms can join to form molecules; water has two hydrogen atoms and one oxygen atom. What are the two particles found in an atom’s nucleus?'
    elif 'force' in q: answer='A force is a push or pull that can change how something moves. For example, pushing a stationary bicycle starts it moving. Force is measured in newtons (N). What force slows a sliding book?'
    elif any(w in q for w in ('quiz','answer','correct')): answer='Let’s work it through one step at a time. First, identify what the question asks. Then choose the fact or formula that applies and check the units. Which part would you like to solve together?'
    else: answer='Let’s make this simple. Start with the main idea, then connect it to something you see every day. Tell me which part feels confusing and we can work through it one step at a time.'
    if context: answer+='\n\nA matching local learning passage was found; its source is listed below.'
    else: answer+='\n\nNo matching local textbook passage was found, so this explanation is general learning help.'
    return answer
