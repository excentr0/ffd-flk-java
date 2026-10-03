"""Conservative FLK source-expression parser. AST records syntax only; it is not executable."""
import re

_TOKEN = re.compile(r'''\s*(?:(\d+(?:\.\d+)?)|([A-Za-zА-Яа-я_][\wА-Яа-я]*)|(>=|<=|!=|==|=|>|<)|([().,+*/-])|('[^']*'|"[^"]*"))''', re.UNICODE)
class _Unsupported(Exception): pass
class _Parser:
    def __init__(self, text):
        self.ts=[]; pos=0
        while pos<len(text):
            m=_TOKEN.match(text,pos)
            if not m: raise _Unsupported(f'unrecognized token at offset {pos}')
            self.ts.append(next(x for x in m.groups() if x is not None)); pos=m.end()
        self.i=0
    def peek(self): return self.ts[self.i] if self.i<len(self.ts) else None
    def take(self, want=None):
        t=self.peek()
        if t is None or (want and t.upper()!=want.upper()): raise _Unsupported(f'expected {want or "token"}, got {t!r}')
        self.i+=1; return t
    def parse(self):
        n=self.boolean()
        if self.peek() is not None: raise _Unsupported(f'unconsumed token {self.peek()!r}')
        return n
    def boolean(self):
        n=self.conjunction()
        while self.peek() and self.peek().upper()=='OR': self.take(); n={'op':'or','args':[n,self.conjunction()]}
        return n
    def conjunction(self):
        n=self.unary()
        while self.peek() and self.peek().upper()=='AND': self.take(); n={'op':'and','args':[n,self.unary()]}
        return n
    def unary(self):
        if self.peek() and self.peek().upper()=='NOT':
            self.take()
            if self.peek() and self.peek().upper()=='EXIST': self.take(); return {'op':'exists','path':self.path(),'negated':True}
            return {'op':'not','arg':self.unary()}
        if self.peek() and self.peek().upper()=='EXIST': self.take(); return {'op':'exists','path':self.path(),'negated':False}
        if self.peek()=='(': self.take(); n=self.boolean(); self.take(')'); return n
        return self.compare()
    def path(self):
        result=[]
        while True:
            name=self.take()
            if not re.fullmatch(r'[A-Za-zА-Яа-я_][\wА-Яа-я]*',name): raise _Unsupported('expected path name')
            tag=None
            if self.peek()=='(':
                self.take(); tag=self.take(); self.take(')')
                if not tag.isdigit() or not 0 <= int(tag) <= 65535:
                    raise _Unsupported('tag annotation must be UInt16 integer')
            result.append({'name':name,'tag':int(tag) if tag is not None else None})
            if self.peek()!='.': break
            self.take()
        return result
    def atom(self):
        t=self.peek()
        if t is None: raise _Unsupported('missing value')
        if t.upper()=='LENGTH': self.take(); self.take('('); p=self.path(); self.take(')'); return {'op':'length','path':p}
        if t=='(': self.take(); n=self.arith(); self.take(')'); return n
        if re.fullmatch(r'\d+(?:\.\d+)?',t): self.take(); return {'type':'number','value':t}
        if t.startswith(("'",'"')): self.take(); return {'type':'literal','value':t[1:-1]}
        if re.fullmatch(r'[A-Za-zА-Яа-я_][\wА-Яа-я]*',t): return {'type':'path','path':self.path()}
        raise _Unsupported(f'unexpected value {t!r}')
    def product(self):
        n=self.atom()
        while self.peek()=='*':
            op=self.take(); n={'op':op,'left':n,'right':self.atom()}
        return n
    def arith(self):
        n=self.product()
        while self.peek() in ('+','-'):
            op=self.take(); n={'op':op,'left':n,'right':self.product()}
        return n
    def compare(self):
        left=self.arith()
        if self.peek() and self.peek().upper()=='IN':
            self.take(); self.take('('); vals=[]
            while True:
                v=self.atom()
                if v.get('type') not in ('number','literal'): raise _Unsupported('IN accepts literal values only')
                vals.append(v)
                if self.peek()!=',': break
                self.take()
            self.take(')'); return {'op':'in','value':left,'set':vals}
        op=self.peek()
        if op not in ('=','==','!=','>','<','>=','<='): raise _Unsupported('expected comparison operator')
        self.take(); return {'op':{'==':'='}.get(op,op),'left':left,'right':self.arith()}
def parse_expression(text):
    try: return {'status':'parsed','ast':_Parser(text.strip()).parse(),'reason':None}
    except (_Unsupported, ValueError) as e: return {'status':'unsupported','ast':None,'reason':str(e)}
