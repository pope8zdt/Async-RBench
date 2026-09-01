from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-cross-app-artifact-7bfdfeaa3c'; assert closure['source_task_id']=='coding:066'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_music_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='music_collaborator'; app=m.MusicCollaborator(); assert app.create_project('song','ana')=='song'
    assert_closure('music_collaboration_playback_closure')

def test_music_midi_tempo_track_order_and_schema():
    m=load_solution(); app=m.MusicCollaborator(); events=[{'track':2,'tick':0,'note':64,'velocity':80},{'track':1,'tick':480,'note':62,'velocity':90},{'track':1,'tick':0,'note':60,'velocity':100}]
    out=app.import_midi(events,480,120); assert [(e['track'],e['tick']) for e in out]==[(1,0),(1,480),(2,0)]; assert out[1]['seconds']==0.5

def test_music_collaboration_lyrics_versions_and_chat_are_preserved():
    m=load_solution(); app=m.MusicCollaborator(); app.create_project('song','ana'); app.join('song','bo'); app.add_element('song','bo','melody',[60,64]); v=app.save_version('song'); insight=app.edit_lyrics('song','Love is bright at night'); app.chat('song','ana','keep chorus'); app.revert('song',v)
    assert insight['sentiment']=='positive'; assert app.projects['song']['elements'][0]['kind']=='melody'; assert app.projects['song']['users']=={'ana','bo'}

def test_music_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert receipt['authority']['track_order']=='track_then_tick'; assert closure['preserved_workflows']==['lyrics','chat','versions','collaborators']; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
