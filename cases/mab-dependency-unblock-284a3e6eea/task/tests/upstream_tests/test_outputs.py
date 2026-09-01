from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'order':['diet','exercise','mental_health'],'exercise_uses_nutrition':True,'mental_uses_both':True}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('wellness_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_wellness_output_schema_weekly_plan_and_closure():
 m=load_solution(); w=m.WellnessJourney(); w.add_user('u',['plant'],['nuts'],['energy']); w.apply_dependency_contract(CONTRACT); assert len(w.create_meal_plan('u',range(1,8)))==7; r,c=docs(); assert m.DOMAIN=='wellness_journey' and c['artifact_type']=='holistic_wellness_dependency_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_wellness_diet_exercise_mental_dependency_behavior():
 m=load_solution(); w=m.WellnessJourney(); w.add_user('u',['plant'],[],['energy']); w.apply_dependency_contract(CONTRACT)
 try:w.create_workout_plan('u',[('run',30,'run.mp4')])
 except RuntimeError:pass
 else:raise AssertionError('exercise bypassed diet')
 w.create_meal_plan('u',range(1,8)); w.log_nutrition('u',2000,80); plan=w.create_workout_plan('u',[('run',30,'run.mp4')]); w.complete_workout('u','run'); w.track_mood('u',2,'stressed'); assert plan[0]['video']=='run.mp4' and w.create_mental_health_plan('u')['meditation']=='breathing'
def test_wellness_nutrition_workout_mood_and_history_are_preserved():
 m=load_solution(); w=m.WellnessJourney(); w.add_user('u',['veg'],['dairy'],['sleep']); w.apply_dependency_contract(CONTRACT); w.create_meal_plan('u',range(1,8)); w.log_nutrition('u',1800,70); w.create_workout_plan('u',[('yoga',20,'yoga.mp4')]); w.complete_workout('u','yoga'); w.track_mood('u',4,'calm'); w.create_mental_health_plan('u'); assert w.nutrition and w.exercise_log and w.moods and w.mental_plans['u']['diet_goal']=='sleep'
def test_wellness_dependency_event_and_final_reverification():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='holistic_wellness_dependency_v2' and r['authority']['order']==['diet','exercise','mental_health'] and r['authority']['mental_uses_both'] is True; assert c['preserved_workflows']==['diet_preferences_and_meals','nutrition_history','workout_schedule_and_videos','mood_and_mental_health_history']
