DOMAIN = 'multiagent_project_manager'
TRANSITIVE_READINESS = True
PRESERVE_AUDIT_HISTORY = True
EVENT_SCHEMA = 'cycle_safe_dependency_v2'

class MultiAgentProjectManager:
    def __init__(self):
        self.projects={}; self.users={}; self.notifications=[]; self.history=[]
    def add_user(self,user,role):
        if role not in {'Project Manager','Team Lead','Team Member'}: raise ValueError('invalid role')
        self.users[user]=role
    def create_project(self,project,user):
        if self.users.get(user)!='Project Manager': raise PermissionError('manager required')
        self.projects[project]={'tasks':{},'status':'pending'}
    def add_task(self,project,task_id,description,deadline,dependencies=(),assignee=None):
        if task_id in dependencies: raise ValueError('self dependency')
        tasks=self.projects[project]['tasks']; tasks[task_id]={'description':description,'deadline':deadline,'dependencies':list(dependencies),'assignee':assignee,'status':'pending'}
        if self._has_cycle(tasks): del tasks[task_id]; raise ValueError('cycle')
        if PRESERVE_AUDIT_HISTORY: self.history.append(('created',project,task_id))
    def _has_cycle(self,tasks):
        visiting=set(); done=set()
        def visit(task):
            if task in visiting: return True
            if task in done or task not in tasks: return False
            visiting.add(task)
            if any(visit(dep) for dep in tasks[task]['dependencies']): return True
            visiting.remove(task); done.add(task); return False
        return any(visit(task) for task in tasks)
    def ready(self,project,task_id):
        tasks=self.projects[project]['tasks']; direct=tasks[task_id]['dependencies']
        if not TRANSITIVE_READINESS: return all(tasks[d]['status']=='completed' for d in direct)
        seen=set()
        def complete(dep):
            if dep in seen: return True
            seen.add(dep); return tasks[dep]['status']=='completed' and all(complete(parent) for parent in tasks[dep]['dependencies'])
        return all(complete(dep) for dep in direct)
    def start(self,project,task_id,user):
        task=self.projects[project]['tasks'][task_id]
        if task['assignee']!=user or not self.ready(project,task_id): raise RuntimeError('task blocked')
        task['status']='in_progress'; self.notifications.append((user,'task_started',task_id))
    def complete(self,project,task_id,user):
        task=self.projects[project]['tasks'][task_id]
        if task['assignee']!=user: raise PermissionError('assignee required')
        task['status']='completed'; self.notifications.append((user,'task_completed',task_id))
        if PRESERVE_AUDIT_HISTORY: self.history.append(('completed',project,task_id))
        tasks=self.projects[project]['tasks']; self.projects[project]['status']='completed' if all(t['status']=='completed' for t in tasks.values()) else 'in_progress'
    def dashboard(self,project):
        tasks=self.projects[project]['tasks']; return {tid:{'status':t['status'],'blocking':[d for d in t['dependencies'] if tasks[d]['status']!='completed']} for tid,t in tasks.items()}
