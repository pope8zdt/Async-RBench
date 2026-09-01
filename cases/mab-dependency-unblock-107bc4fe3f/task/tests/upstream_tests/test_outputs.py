from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); PROTOCOL={'roles':{'scout':['inspect','message'],'builder':['move_block','message'],'navigator':['move_player','message']},'requires_expected_version':True,'collision_policy':'reject_occupied_destination'}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('maze_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_maze_output_schema_layout_and_artifacts():
 m=load_solution(); maze=m.MultiAgentMaze(4,3,walls=[(1,1)],exit_cell=(3,2),difficulty='hard'); assert m.DOMAIN=='multi_agent_maze' and maze.exit==(3,2) and maze.difficulty=='hard'; r,c=docs(); assert c['artifact_type']=='versioned_maze_collaboration_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_maze_role_version_collision_block_move_and_path_behavior():
 m=load_solution(); maze=m.MultiAgentMaze(4,3,walls=[(1,1)],exit_cell=(3,2)); maze.add_player('b','builder',(0,0)); maze.add_player('n','navigator',(0,1)); maze.add_player('s','scout',(0,2)); maze.add_block('box',(1,0)); maze.apply_transition_protocol(PROTOCOL); assert maze.move_block('b','box',(2,0),0)==1
 for call,exc in [(lambda:maze.move_block('s','box',(3,0),1),PermissionError),(lambda:maze.move_block('b','box',(3,0),0),RuntimeError),(lambda:maze.move_block('b','box',(0,1),1),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('invalid transition accepted')
 assert maze.path_exists((0,1)) is True
def test_maze_messages_progress_tutorial_and_achievements_are_preserved():
 m=load_solution(); maze=m.MultiAgentMaze(2,2,exit_cell=(1,1)); maze.add_player('n','navigator',(0,0)); maze.apply_transition_protocol(PROTOCOL); maze.message('n','move east then south'); maze.complete_tutorial('n','movement'); maze.move_player('n',(1,0),0); maze.move_player('n',(1,1),1); snap=maze.save_progress('team')
 assert maze.messages[0]['text']=='move east then south' and 'movement' in maze.tutorial['n'] and ('n','maze_complete') in maze.achievements and snap['version']==2 and maze.load_progress('team')['blocks']=={}
def test_maze_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='maze_transition_protocol_v2' and r['authority']['requires_expected_version'] is True and r['authority']['collision_policy']=='reject_occupied_destination' and set(r['authority']['roles'])=={'scout','builder','navigator'}; assert c['upstream_depth']==4 and c['preserved_workflows']==['maze_layout','collaboration_messages','saved_progress','tutorial_and_achievements']
