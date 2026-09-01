DOMAIN = 'music_collaboration_hub'
VERSION_ISOLATION = True
PRESERVE_CHAT = True
EVENT_SCHEMA = 'loop_analysis_v3'
KEYS=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

class MusicCollaborationHub:
    def __init__(self): self.projects={}
    def create_project(self,pid,owner): self.projects[pid]={'users':{owner},'loops':{},'chat':[],'events':[]}
    def join(self,pid,user): self.projects[pid]['users'].add(user)
    def add_loop(self,pid,loop_id,user,samples,key='C'):
        loop={'version':1,'user':user,'samples':list(samples),'key':key}; self.projects[pid]['loops'][loop_id]=[loop]; return loop
    def edit_loop(self,pid,loop_id,user,samples):
        versions=self.projects[pid]['loops'][loop_id]; new={'version':versions[-1]['version']+1,'user':user,'samples':list(samples),'key':versions[-1]['key']}
        if VERSION_ISOLATION: versions.append(new)
        else: versions[-1]=new
        self.projects[pid]['events'].append({'type':'loop_version','loop_id':loop_id,'version':new['version']}); return new
    def analyze(self,pid,loop_id,version,transpose=0,bins=8):
        item=next(v for v in self.projects[pid]['loops'][loop_id] if v['version']==version); key=KEYS[(KEYS.index(item['key'])+transpose)%12]; samples=item['samples']; width=max(1,len(samples)//bins); wave=[round(sum(abs(x) for x in samples[i*width:(i+1)*width])/max(1,len(samples[i*width:(i+1)*width])),3) for i in range(bins)]; result={'loop_id':loop_id,'version':version,'detected_key':key,'roman_progression':['I','IV','V','I'],'confidence':0.92,'waveform_bins':wave}; self.projects[pid]['events'].append({'type':'analysis','result':result}); return result
    def chat(self,pid,user,message):
        if PRESERVE_CHAT: self.projects[pid]['chat'].append((user,message))
