DOMAIN = 'art_collab'
DEDUPLICATE_OPERATIONS = True

class ArtCollab:
    def __init__(self): self.users={}; self.projects={}
    def register(self,user,password): self.users[user]={'password_hash':'hash:'+password,'authenticated':False}
    def login(self,user,password): self.users[user]['authenticated']=self.users[user]['password_hash']=='hash:'+password; return self.users[user]['authenticated']
    def create_project(self,project,user):
        if not self.users.get(user,{}).get('authenticated'): raise PermissionError('login required')
        self.projects[project]={'revision':0,'layers':{'base':{}},'history':[],'seen':set(),'last_clock':(-1,'')}
    def apply_operation(self,project,op):
        p=self.projects[project]; required={'op_id','base_revision','lamport','actor','payload'}
        if not required<=set(op): raise ValueError('invalid operation')
        if DEDUPLICATE_OPERATIONS and op['op_id'] in p['seen']: return {'status':'duplicate','revision':p['revision'],'op_id':op['op_id']}
        p['seen'].add(op['op_id']); clock=(op['lamport'],op['actor']); conflict=op['base_revision']!=p['revision']
        if not conflict or clock>=p['last_clock']:
            payload=op['payload']; layer=payload.get('layer','base'); p['layers'].setdefault(layer,{})[tuple(payload['point'])]=payload['color']; p['last_clock']=clock
        p['revision']+=1; p['history'].append(dict(op))
        return {'status':'conflict_resolved' if conflict else 'applied','revision':p['revision'],'op_id':op['op_id']}
    def snapshot(self,project):
        p=self.projects[project]; return {'revision':p['revision'],'layers':{k:dict(v) for k,v in p['layers'].items()},'history_count':len(p['history'])}
