from copy import deepcopy

DOMAIN = 'music_collaborator'
TRACK_ORDER_POLICY = 'track_then_tick'

class MusicCollaborator:
    def __init__(self):
        self.projects = {}

    def create_project(self, project_id, owner):
        self.projects[project_id] = {'users': {owner}, 'elements': [], 'lyrics': [], 'chat': [], 'versions': []}
        return project_id

    def join(self, project_id, user):
        self.projects[project_id]['users'].add(user)

    def add_element(self, project_id, user, kind, value):
        if user not in self.projects[project_id]['users'] or kind not in {'note', 'melody', 'harmony'}: raise ValueError('invalid collaborator or element')
        self.projects[project_id]['elements'].append({'user': user, 'kind': kind, 'value': value})

    def import_midi(self, events, ticks_per_beat=480, tempo_bpm=120):
        required = {'track', 'tick', 'note', 'velocity'}
        if any(not required <= set(e) for e in events): raise ValueError('invalid MIDI event')
        ordered = sorted(events, key=lambda e: (e['track'], e['tick'])) if TRACK_ORDER_POLICY == 'track_then_tick' else list(events)
        beat_seconds = 60.0 / tempo_bpm
        return [{**e, 'seconds': round(e['tick'] / ticks_per_beat * beat_seconds, 6)} for e in ordered]

    def edit_lyrics(self, project_id, text):
        insight = {'sentiment': 'positive' if any(w in text.lower() for w in ('love','bright','joy')) else 'neutral', 'themes': sorted({w for w in ('love','night','home') if w in text.lower()})}
        self.projects[project_id]['lyrics'].append({'text': text, 'insight': insight}); return insight

    def chat(self, project_id, user, message):
        self.projects[project_id]['chat'].append((user, message))

    def save_version(self, project_id):
        p=self.projects[project_id]; snapshot=deepcopy({k:v for k,v in p.items() if k!='versions'}); p['versions'].append(snapshot); return len(p['versions'])-1

    def revert(self, project_id, version):
        versions=self.projects[project_id]['versions']; restored=deepcopy(versions[version]); restored['versions']=versions; self.projects[project_id]=restored

    def suggest_harmony(self, root):
        return {'C':'G','D':'A','E':'B','F':'C','G':'D','A':'E','B':'F#'}.get(root, 'C')
