DOMAIN='budget_sync'
EVENT_SCHEMA='shared_budget_policy_v2'
USE_COMPLETE_BUDGET_POLICY = True
PRESERVE_FINANCIAL_HISTORY = True
class BudgetSync:
 def __init__(self): self.users={}; self.budgets={}; self.notifications=[]; self.feedback=[]; self.contract=None
 def add_user(self,user_id,profile):
  if not user_id or user_id in self.users: raise ValueError('unique user required')
  self.users[user_id]={'profile':dict(profile)}
 def apply_budget_policy(self,contract):
  if contract.get('money_unit')!='integer_cents' or set(contract.get('roles',[]))!={'owner','edit','view'}: raise ValueError('incomplete policy')
  self.contract=dict(contract); return self.contract
 def create_budget(self,budget_id,owner,name,categories,goal_cents):
  if owner not in self.users or goal_cents<0 or not categories: raise ValueError('invalid budget')
  self.budgets[budget_id]={'name':name,'owner':owner,'members':{owner:'owner'},'categories':set(categories),'goal_cents':int(goal_cents),'transactions':[],'preferences':{'chart':'pie'}}; return self.budgets[budget_id]
 def invite(self,actor,budget_id,user_id,role):
  b=self.budgets[budget_id]
  if actor!=b['owner'] or user_id not in self.users or role not in {'edit','view'}: raise PermissionError('owner invitation required')
  b['members'][user_id]=role
  if PRESERVE_FINANCIAL_HISTORY:self.notifications.append({'budget':budget_id,'kind':'member_added','user':user_id})
 def add_transaction(self,user_id,budget_id,kind,category,amount_cents):
  b=self.budgets[budget_id]
  if b['members'].get(user_id) not in {'owner','edit'} or kind not in {'income','expense'} or category not in b['categories'] or not isinstance(amount_cents,int) or amount_cents<=0: raise PermissionError('invalid transaction')
  row={'user':user_id,'kind':kind,'category':category,'amount_cents':amount_cents}; b['transactions'].append(row); self._notify_limits(budget_id); return row
 def _notify_limits(self,budget_id):
  if USE_COMPLETE_BUDGET_POLICY and not self.contract: raise RuntimeError('budget policy required')
  b=self.budgets[budget_id]; income=sum(t['amount_cents'] for t in b['transactions'] if t['kind']=='income'); expenses=sum(t['amount_cents'] for t in b['transactions'] if t['kind']=='expense')
  if income and expenses*100>=income*int(self.contract['spending_alert_percent']): self.notifications.append({'budget':budget_id,'kind':'spending_limit_exceeded'})
  if income-expenses>=b['goal_cents']: self.notifications.append({'budget':budget_id,'kind':'goal_reached'})
 def dashboard(self,user_id,budget_id):
  b=self.budgets[budget_id]
  if user_id not in b['members']: raise PermissionError('budget unavailable')
  income=sum(t['amount_cents'] for t in b['transactions'] if t['kind']=='income'); expenses=[t for t in b['transactions'] if t['kind']=='expense']; breakdown={c:sum(t['amount_cents'] for t in expenses if t['category']==c) for c in sorted(b['categories'])}
  return {'balance_cents':income-sum(breakdown.values()),'spending_breakdown':breakdown,'goal_progress_cents':income-sum(breakdown.values()),'chart':b['preferences']['chart']}
 def suggestions(self,budget_id):
  b=self.budgets[budget_id]; d=self.dashboard(b['owner'],budget_id); total=sum(d['spending_breakdown'].values()); return [f'reduce:{c}' for c,v in d['spending_breakdown'].items() if total and v*2>total]
 def set_chart(self,user_id,budget_id,chart):
  if chart not in {'pie','bar'} or user_id not in self.budgets[budget_id]['members']: raise ValueError('invalid chart')
  self.budgets[budget_id]['preferences']['chart']=chart
 def submit_feedback(self,user_id,text):
  if user_id not in self.users or not text: raise ValueError('invalid feedback')
  if PRESERVE_FINANCIAL_HISTORY:self.feedback.append({'user':user_id,'text':text})
