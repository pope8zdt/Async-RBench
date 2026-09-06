"""Derive public corpus counts; never serialize case contracts or verifier data."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import yaml


def build_catalog(root: Path) -> dict:
    raw = (root / 'cases/registry.json').read_bytes()
    registry = json.loads(raw)
    taxonomy = json.loads((root / 'event_taxonomy.json').read_bytes())
    themes = [entry['id'] for entry in taxonomy['event_themes']]
    if len(themes) != len(set(themes)) or not themes:
        raise ValueError('Invalid event theme taxonomy')
    cases, instances = Counter(), Counter()
    seen = set()
    ids = set()
    for entry in registry['case_families']:
        case_id = entry['case_id']
        if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', case_id) or case_id in ids:
            raise ValueError('Invalid or duplicate registered case')
        ids.add(case_id)
        case_root = (root / 'cases' / case_id).resolve()
        if not case_root.is_relative_to((root / 'cases').resolve()):
            raise ValueError('Case escapes repository')
        # Theme metadata is evaluator-owned. Only the single classification value leaves this function.
        case_contract = yaml.safe_load((case_root / 'private/private_case.yaml').read_text(encoding='utf-8'))
        theme = case_contract['classification']['primary_event_theme']
        if theme not in themes:
            raise ValueError('Unknown registered case theme')
        cases[theme] += 1
        if not entry['instances']:
            raise ValueError('Registered case has no instances')
        for instance in entry['instances']:
            key = (case_id, instance['instance_id'])
            if key in seen:
                raise ValueError('Duplicate registered instance')
            seen.add(key)
            instance_root = (case_root / instance['path']).resolve()
            if not instance_root.is_relative_to(case_root):
                raise ValueError('Instance escapes case directory')
            contract = yaml.safe_load((instance_root / 'private/private_case.yaml').read_text(encoding='utf-8'))
            instance_theme = contract['classification']['primary_event_theme']
            if instance_theme not in themes:
                raise ValueError('Unknown registered instance theme')
            instances[instance_theme] += 1
    if not ids:
        raise ValueError('Empty registered corpus')
    return {'caseCount': len(ids), 'instanceCount': len(seen),
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'registrySha256': hashlib.sha256(raw).hexdigest(),
            'themes': [{'id': theme, 'caseCount': cases[theme], 'instanceCount': instances[theme]} for theme in themes]}
