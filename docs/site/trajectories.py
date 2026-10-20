"""Opt-in, read-only export of reviewed log fields for a local website preview.

This module never imports the benchmark runner, executes log commands, or scores a run.
Raw logs and the curation manifest remain outside the public website checkout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

TYPES = {
    'episode_started', 'episode_ended', 'child_spawned', 'child_started',
    'child_completed', 'child_cancelled', 'child_failed', 'result_available',
    'result_delivered', 'result_presented', 'adapter_queued',
    'result_delivery_evaluator_fact', 'main_action', 'main_action_finished',
    'child_path_promotion_result', 'finish_invoked',
}
FIELDS = {
    'child_id', 'workstream_id', 'work_units', 'completion_id', 'delivery_occurrence_id',
    'replayed', 'replay_of_completion_id', 'replay_of_occurrence_id', 'action_id',
    'kind', 'tool', 'decision', 'source_path', 'destination_path', 'exit_code',
    'success', 'reason', 'initiated_by', 'local_status', 'requested_status',
}
EXTRA = {'command', 'command_excerpt', 'evidence'}
# Fail closed for common credentials, private evaluation paths, and private-key blocks.
UNSAFE = re.compile(r'(?i)(?:sk-[a-z0-9_-]{16,}|(?:api[_-]?key|access[_-]?token|password|authorization)\s*[=:]\s*[^\s,}]+|-----BEGIN [\w ]*PRIVATE KEY|/async_rbench/(?:upstream_solutions|hidden)|secret\[[^\]]+\]|[A-Z]:[\\/]Users[\\/])')


def check_text(value):
    if UNSAFE.search(json.dumps(value, ensure_ascii=False)):
        raise ValueError('Sensitive content found in reviewed export; remove that field from curation')


def export_case(spec):
    source = Path(spec['source'])
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != spec['source_sha256']:
        raise ValueError('Source digest changed; review the curation manifest')
    records = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    events, lanes = [], {'main': 'Main agent', 'delivery': 'Result delivery'}
    commands = set(spec.get('commands', []))
    excerpts = spec.get('excerpts', {})
    evidence = spec.get('evidence', {})
    for entry in records:
        if entry.get('episode_id') != spec['episode_id']:
            raise ValueError('Mixed episode source')
        kind, seq = entry['type'], entry['seq']
        if kind not in TYPES:
            continue
        record = {k: entry[k] for k in FIELDS if entry.get(k) is not None}
        if seq in commands:
            if kind != 'main_action' or not isinstance(entry.get('command'), str):
                raise ValueError('Reviewed command does not exist')
            record['command'] = entry['command']
        if str(seq) in excerpts:
            selected = excerpts[str(seq)]
            if not selected or any(line not in entry.get('command', '') for line in selected):
                raise ValueError('Command excerpt is not verbatim source text')
            record['command_excerpt'] = '\n[… excerpt …]\n'.join(selected)
        if str(seq) in evidence:
            observed = entry.get('payload', {}).get('evidence', {})
            record['evidence'] = {key: observed[key] for key in evidence[str(seq)]}
        child = entry.get('child_id')
        if child:
            lanes.setdefault(child, ' / '.join(entry.get('work_units', [])) or child)
        if kind.startswith('result_') or kind == 'adapter_queued':
            lane = 'delivery'
        elif kind.startswith('child_') and kind != 'child_path_promotion_result':
            lane = child or 'delivery'
        else:
            lane = 'main'
        events.append(dict(seq=seq, event_id=entry['event_id'], elapsed_ms=entry['elapsed_ms'],
                           type=kind, lane=lane, record=record))
    exported = {e['seq'] for e in events}
    if not (commands | {int(k) for k in excerpts} | {int(k) for k in evidence}) <= exported:
        raise ValueError('Curation references an omitted event')
    result = {key: spec[key] for key in ('id', 'title', 'description', 'model', 'episode_id', 'milestones')}
    result.update(source_sha256=digest, source_name='event_source.jsonl', mode='async',
                  lanes=[dict(id=k, label=v) for k, v in lanes.items()], events=events,
                  source_event_count=len(records))
    validate_bundle(dict(version=1, local_only=True, cases=[result]))
    return result


def validate_bundle(bundle):
    def exact(value, keys):
        if not isinstance(value, dict) or set(value) != set(keys):
            raise ValueError('Unexpected trajectory fields')

    def label(value):
        exact(value, ('zh', 'en'))
        if not all(isinstance(v, str) and 0 < len(v) <= 1500 for v in value.values()):
            raise ValueError('Invalid bilingual label')

    exact(bundle, ('version', 'local_only', 'cases'))
    if bundle['version'] != 1 or bundle['local_only'] is not True or not 1 <= len(bundle['cases']) <= 3:
        raise ValueError('Only local showcase bundles are supported')
    ids = set()
    for case in bundle['cases']:
        exact(case, ('id', 'title', 'description', 'model', 'episode_id', 'milestones', 'source_sha256',
                     'source_name', 'mode', 'lanes', 'events', 'source_event_count'))
        if not re.fullmatch(r'[a-z0-9-]+', case['id']) or case['id'] in ids:
            raise ValueError('Invalid or duplicate case id')
        ids.add(case['id'])
        label(case['title']); label(case['description'])
        if case['mode'] != 'async' or case['source_name'] != 'event_source.jsonl' or not re.fullmatch(r'[0-9a-f]{64}', case['source_sha256']):
            raise ValueError('Invalid provenance')
        lane_ids = set()
        for lane in case['lanes']:
            exact(lane, ('id', 'label'))
            if not re.fullmatch(r'main|delivery|child-\d+', lane['id']) or lane['id'] in lane_ids:
                raise ValueError('Invalid lane')
            lane_ids.add(lane['id'])
        previous_seq, previous_time, event_ids, seqs = 0, -1, set(), set()
        if not 1 <= len(case['events']) <= 5000:
            raise ValueError('Invalid event count')
        for event in case['events']:
            exact(event, ('seq', 'event_id', 'elapsed_ms', 'type', 'lane', 'record'))
            seq, ms = event['seq'], event['elapsed_ms']
            if (not isinstance(seq, int) or seq <= previous_seq or
                not isinstance(ms, (float, int)) or not math.isfinite(ms) or ms < previous_time or
                event['event_id'] != f"{case['episode_id']}:{seq}" or event['event_id'] in event_ids or
                event['type'] not in TYPES or event['lane'] not in lane_ids):
                raise ValueError('Invalid identity, time or event order')
            if not isinstance(event['record'], dict) or set(event['record']) - FIELDS - EXTRA:
                raise ValueError('Unexpected record fields')
            if len(json.dumps(event['record'])) > 20000:
                raise ValueError('Oversized reviewed record')
            previous_seq, previous_time = seq, ms
            event_ids.add(event['event_id']); seqs.add(seq)
        seen_milestones = set()
        for item in case['milestones']:
            exact(item, ('seq', 'title', 'note'))
            if item['seq'] not in seqs or item['seq'] in seen_milestones:
                raise ValueError('Milestone must reference one exported event')
            seen_milestones.add(item['seq'])
            label(item['title']); label(item['note'])
        if not seen_milestones:
            raise ValueError('At least one key moment is required')
        check_text(case)
    return bundle


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    bundle = dict(version=1, local_only=True,
                  cases=[export_case(c) for c in json.loads(args.manifest.read_text(encoding='utf-8'))['cases']])
    validate_bundle(bundle)
    # Refuse overwrite: edits require a fresh, explicit export destination.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(bundle, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'cases': len(bundle['cases']), 'events': [len(c['events']) for c in bundle['cases']]}))
