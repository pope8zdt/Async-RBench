from copy import deepcopy
DOMAIN='multi_agent_quest_creator'
STRUCTURED_BALANCE = True
PRESERVE_VERSION_HISTORY = True
EVENT_SCHEMA='quest_balance_v2'
class QuestCreator:
 def __init__(self): self.quests={}; self.ratings=[]
 def create(self,qid,owner,quest_type,enemies,reward,objectives): self.quests[qid]={'collaborators':{owner},'versions':[{'version':1,'type':quest_type,'enemies':list(enemies),'reward':reward,'objectives':list(objectives)}],'simulations':[]}
 def balance(self,qid,player_skill):
  q=self.quests[qid]['versions'][-1]; strength=sum(e['strength'] for e in q['enemies']); difficulty=round(strength/max(player_skill,1)*10+len(q['objectives'])*2,2); fairness='fair' if .7*strength<=q['reward']<=1.5*strength else ('under_rewarded' if q['reward']<.7*strength else 'over_rewarded'); adjustments=[{'field':'enemy_count','delta':-1,'expected_difficulty_delta':-2} if difficulty>15 else {'field':'enemy_count','delta':1,'expected_difficulty_delta':2},{'field':'reward','delta':max(0,strength-q['reward']),'expected_fairness':'fair'}]
  if not STRUCTURED_BALANCE:return difficulty
  return {'quest_version':q['version'],'difficulty_score':difficulty,'fairness_band':fairness,'ranked_adjustments':adjustments}
 def apply_adjustment(self,qid,result,index,actor):
  if actor not in self.quests[qid]['collaborators']:raise PermissionError('collaborator required')
  current=self.quests[qid]['versions'][-1]; new=deepcopy(current); new['version']+=1; adj=result['ranked_adjustments'][index]
  if adj['field']=='enemy_count' and adj['delta']<0:new['enemies']=new['enemies'][:adj['delta']]
  if adj['field']=='reward':new['reward']+=adj['delta']
  if PRESERVE_VERSION_HISTORY:self.quests[qid]['versions'].append(new)
  else:self.quests[qid]['versions']=[new]
  return new
 def revert(self,qid,version): return deepcopy(next(v for v in self.quests[qid]['versions'] if v['version']==version))
 def simulate(self,qid,seed): result={'version':self.quests[qid]['versions'][-1]['version'],'seed':seed,'success':seed%2==0}; self.quests[qid]['simulations'].append(result); return result
