DOMAIN = 'team_sync_pro'
PRIORITY_FIRST = True

class TeamSyncPro:
    def __init__(self): self.members={}; self.tasks={}; self.messages=[]; self.meetings=[]; self.notifications=[]; self.schedule={}
    def add_member(self, member, slots): self.members[member]=list(slots)
    def add_task(self, task_id, duration, priority, dependencies=()): self.tasks[task_id]={'duration':duration,'priority':priority,'dependencies':list(dependencies),'complete':False}
    def message(self, sender, text): self.messages.append({'sender':sender,'text':text})
    def schedule_tasks(self):
        order=sorted(self.tasks, key=lambda t:(-self.tasks[t]['priority'],t)) if PRIORITY_FIRST else sorted(self.tasks)
        assigned={}; used=set(); pending=set(order)
        while pending:
            progress=False
            for task in order:
                if task not in pending: continue
                deps=self.tasks[task]['dependencies']
                if any(d not in assigned and not self.tasks.get(d,{}).get('complete') for d in deps): continue
                choice=next(((m,s) for m,slots in sorted(self.members.items()) for s in slots if (m,s) not in used),None)
                if choice: assigned[task]={'member':choice[0],'slot':choice[1],'duration':self.tasks[task]['duration']}; used.add(choice)
                else: assigned[task]={'unassigned_reason':'no_available_slot'}
                pending.remove(task); progress=True
            if not progress:
                for task in sorted(pending): assigned[task]={'unassigned_reason':'unmet_dependency'}
                break
        return assigned
    def apply_adaptive_schedule(self):
        old=dict(self.schedule); self.schedule=self.schedule_tasks()
        for task,value in self.schedule.items():
            if old.get(task)!=value and 'member' in value: self.notifications.append({'member':value['member'],'task':task,'kind':'assignment_or_time_change'})
        return self.schedule
    def productivity_report(self):
        return {'assigned':sum('member' in v for v in self.schedule.values()),'completed':sum(t['complete'] for t in self.tasks.values()),'contributions':{m:sum(v.get('member')==m for v in self.schedule.values()) for m in self.members}}
