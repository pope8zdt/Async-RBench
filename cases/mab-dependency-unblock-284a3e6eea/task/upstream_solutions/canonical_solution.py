DOMAIN='wellness_journey'
EVENT_SCHEMA='holistic_wellness_dependency_v2'
ENFORCE_WELLNESS_DEPENDENCIES = True
PRESERVE_WELLNESS_HISTORY = True
class WellnessJourney:
 def __init__(self): self.users={}; self.meal_plans={}; self.nutrition=[]; self.workouts={}; self.exercise_log=[]; self.moods=[]; self.mental_plans={}; self.contract=None
 def add_user(self,user_id,preferences,restrictions,goals): self.users[user_id]={'preferences':list(preferences),'restrictions':list(restrictions),'goals':list(goals)}
 def apply_dependency_contract(self,contract):
  if contract.get('order')!=['diet','exercise','mental_health'] or not contract.get('exercise_uses_nutrition') or not contract.get('mental_uses_both'): raise ValueError('invalid dependency contract')
  self.contract=dict(contract); return self.contract
 def create_meal_plan(self,user_id,days):
  if user_id not in self.users or set(days)!=set(range(1,8)): raise ValueError('weekly plan required')
  plan={day:{'meal':f'meal-{day}','restrictions':list(self.users[user_id]['restrictions'])} for day in sorted(days)}; self.meal_plans[user_id]=plan; return plan
 def log_nutrition(self,user_id,calories,protein):
  if user_id not in self.meal_plans or calories<=0 or protein<0: raise ValueError('diet plan required')
  row={'user':user_id,'calories':calories,'protein':protein}
  if PRESERVE_WELLNESS_HISTORY:self.nutrition.append(row)
  return row
 def create_workout_plan(self,user_id,sessions):
  if ENFORCE_WELLNESS_DEPENDENCIES and (not self.contract or user_id not in self.meal_plans or not any(x['user']==user_id for x in self.nutrition)): raise RuntimeError('diet dependency unresolved')
  plan=[{'name':name,'duration':duration,'video':video,'nutrition_target':self.nutrition[-1]['calories']} for name,duration,video in sessions]; self.workouts[user_id]=plan; return plan
 def complete_workout(self,user_id,name):
  if name not in {x['name'] for x in self.workouts.get(user_id,[])}: raise ValueError('unknown workout')
  if PRESERVE_WELLNESS_HISTORY:self.exercise_log.append({'user':user_id,'name':name})
 def track_mood(self,user_id,score,note):
  if not 1<=score<=5: raise ValueError('invalid mood')
  row={'user':user_id,'score':score,'note':note}; self.moods.append(row); return row
 def create_mental_health_plan(self,user_id):
  if ENFORCE_WELLNESS_DEPENDENCIES and (user_id not in self.workouts or not any(x['user']==user_id for x in self.exercise_log)): raise RuntimeError('exercise dependency unresolved')
  recent=[x['score'] for x in self.moods if x['user']==user_id]; stress='breathing' if recent and min(recent)<=2 else 'body scan'; plan={'meditation':stress,'stress_tip':'schedule recovery after training','diet_goal':self.users[user_id]['goals'][0]}; self.mental_plans[user_id]=plan; return plan
