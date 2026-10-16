"""Validate and build the reviewed, editable public-site snapshot.

No model calls, private judge access or raw trace import occur during a build.
The snapshot is kept at root-relative URLs; deployment adds its project prefix.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

SITE = Path(__file__).resolve().parent
TEXT_EXTENSIONS = {'.html', '.css', '.mjs', '.svg', '.json', '.yaml', '.csv', '.cff', '.md', '.txt'}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | {'.png', '.pdf', '.woff2'}
CASE_POINTS = {
    'release': {165, 180, 195, 228, 289, 303, 315, 316, 546},
    'replay': {292, 317, 432, 720, 722, 754, 800, 817, 995},
    'early-stop': {229, 264, 265, 300, 319, 359, 367, 368, 428, 430},
    'reconsider': {305, 382, 684}, 'defer': {146, 150, 316}, 'continue': {387, 476, 505},
}
RECORD_FIELDS = {
    'action_id', 'child_id', 'command', 'command_excerpt', 'completion_id', 'decision',
    'delivery_occurrence_id', 'destination_path', 'evidence', 'exit_code', 'kind',
    'local_status', 'replayed', 'requested_status', 'source_path', 'success', 'tool',
    'work_units', 'workstream_id', 'replay_of_completion_id', 'replay_of_occurrence_id',
    'initiated_by', 'reason',
}
EVENT_FIELDS = {'seq', 'event_id', 'elapsed_ms', 'type', 'lane'}


def public_archive(bundle: dict) -> dict:
    """Select already displayed evidence, never entire model conversations."""
    result = {'version': 1, 'publication': 'reviewed-excerpts-v1', 'cases': []}
    for source in bundle['cases']:
        if source['id'] not in CASE_POINTS:
            raise ValueError('Unreviewed case')
        case = {key: copy.deepcopy(source[key]) for key in (
            'id', 'title', 'description', 'model', 'episode_id', 'milestones',
            'source_sha256', 'mode', 'lanes', 'source_event_count'
        ) if key in source}
        selected = CASE_POINTS[source['id']]
        case['events'] = []
        for event in source['events']:
            # The artifact map also uses the recorded start of its unfinished child.
            map_start = source['id'] == 'early-stop' and event.get('lane') == 'child-2' and event['type'] == 'child_started'
            if event['seq'] not in selected and not map_start:
                continue
            if event['type'] in {'model_reply', 'model_request'}:
                raise ValueError('Model conversation cannot be published')
            clean = {k: copy.deepcopy(v) for k, v in event.items() if k in EVENT_FIELDS}
            clean['record'] = {k: copy.deepcopy(v) for k, v in event.get('record', {}).items() if k in RECORD_FIELDS}
            case['events'].append(clean)
        available = {e['seq'] for e in case['events']}
        case['milestones'] = [m for m in case.get('milestones', []) if m['seq'] in available]
        assert_public_text(json.dumps(case, ensure_ascii=False), 'reviewed case')
        result['cases'].append(case)
    return result


def assert_public_text(text: str, filename: str) -> None:
    patterns = [
        r'(?i)\b(?:sk|ghp|github_pat)-[A-Za-z0-9_-]{24,}',
        r'\bgh[pousr]_[A-Za-z0-9]{30,}',
        r'(?i)Bearer\s+[A-Za-z0-9._-]{20,}',
        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        r'(?i)[A-Z]:[/\\]+(?:Users|private|Async-RBench)(?:[/\\]+)',
        r'(?i)(?:api_key|password|access_token)\s*[=:]\s*[\"\x27]?(?:sk-|ghp_)',
    ]
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError(f'Non-public material found in {filename}')


def prefix_paths(content: str, base: str) -> str:
    """Prefix URL literals only, leaving code paths, fragments and remote URLs alone."""
    base = '/' + base.strip('/') if base.strip('/') else ''
    if not base:
        return content
    # All public route/asset namespaces are explicit; /app in evidence is not a URL.
    roots = r'(?:assets/|data/|paper/|runs/|benchmark/|entry/|tasks/|leaderboard/|evaluate/|overview/|trajectories/|CITATION\.cff|index\.html|[a-z][a-z-]*\.(?:css|mjs))'
    content = re.sub(r'([\"\x27`(])/(?=' + roots + r')', lambda m: m[1] + base + '/', content)
    content = re.sub(r'(href=[\"\x27])/(\??[\"\x27])', lambda m: m[1] + base + '/' + m[2], content)
    content = content.replace('data-base=""', f'data-base="{base}"')
    # Legacy deep links entered on the cover must still reach the same section.
    content = content.replace("url.pathname !== '/'", f"url.pathname !== '{base}/'")
    return content


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and key in {'src', 'href', 'data-src', 'poster'}:
                self.refs.append(value)
            if value and key == 'srcset':
                self.refs.extend(part.strip().split(' ')[0] for part in value.split(','))


def validate_site(root: Path, base: str = '') -> dict:
    root = root.resolve()
    base = '/' + base.strip('/') if base.strip('/') else ''
    errors = []
    files = [p for p in root.rglob('*') if p.is_file()]
    for file in files:
        rel = file.relative_to(root).as_posix()
        if file.is_symlink() or file.suffix not in ALLOWED_EXTENSIONS and file.name not in {'LICENSE', '.nojekyll'}:
            raise ValueError(f'Unexpected published file: {rel}')
        if '.local.' in file.name or file.suffix == '.jsonl':
            raise ValueError(f'Local data file in publication: {rel}')
        if file.suffix not in TEXT_EXTENSIONS and file.name != 'LICENSE':
            continue
        text = file.read_text(encoding='utf-8')
        assert_public_text(text, rel)
        if file.suffix == '.html':
            parser = References()
            parser.feed(text)
            refs = parser.refs
        elif file.suffix in {'.css', '.mjs'}:
            refs = re.findall(r'(?:from\s*|import\s*\(|url\(\s*)[\"\x27]([^\"\x27]+)[\"\x27]', text)
            refs += re.findall(r'[\"\x27`](/(?:assets|data)/[^\"\x27`\s]+)[\"\x27`]', text)
        else:
            refs = []
        for ref in refs:
            if '${' in ref or ref.startswith(('#', 'data:', 'mailto:')):
                continue
            url = urlsplit(ref)
            if url.scheme or url.netloc or not url.path:
                continue
            path = unquote(url.path)
            if path.startswith('/'):
                if base and not path.startswith(base + '/'):
                    errors.append(f'{rel}: URL outside project prefix: {path}')
                    continue
                target = root / path[len(base):].lstrip('/')
            else:
                target = file.parent / path
            target = target.resolve()
            if not target.is_relative_to(root):
                errors.append(f'{rel}: reference escapes site')
            elif not (target.is_file() or (target / 'index.html').is_file()):
                errors.append(f'{rel}: missing {ref}')
    if errors:
        raise ValueError('\n'.join(errors[:30]))
    return {'files': len(files), 'pages': sum(p.suffix == '.html' for p in files)}


def validate_snapshot(source: Path) -> None:
    manifest = json.loads((SITE / 'publication-integrity.json').read_text(encoding='utf-8'))
    for name, expected in manifest['protected'].items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Protected paper data or figure changed: {name}')
    archive = json.loads((source / 'data/trajectories.public.json').read_text(encoding='utf-8'))
    if archive.get('publication') != 'reviewed-excerpts-v1' or {c['id'] for c in archive['cases']} != set(CASE_POINTS):
        raise ValueError('Expected six reviewed trajectory cases')
    for case in archive['cases']:
        if not CASE_POINTS[case['id']].issubset({e['seq'] for e in case['events']}):
            raise ValueError(f'Missing required case records: {case["id"]}')
        if case['events'] != public_archive({'cases': [case]})['cases'][0]['events']:
            raise ValueError('Unreviewed records in public archive')
    validate_site(source)


def build(source: Path, output: Path, base: str) -> dict:
    validate_snapshot(source)
    source, output = source.resolve(), output.resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Build output must be separate from the source snapshot')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new or empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    for file in source.rglob('*'):
        if not file.is_file():
            continue
        target = output / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix in {'.html', '.css', '.mjs'}:
            target.write_text(prefix_paths(file.read_text(encoding='utf-8'), base), encoding='utf-8')
        else:
            shutil.copyfile(file, target)
    return validate_site(output, base)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SITE / 'published')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--base-path', default='')
    args = parser.parse_args()
    if args.output:
        print(json.dumps(build(args.source, args.output, args.base_path)))
    else:
        validate_snapshot(args.source)
        print(json.dumps(validate_site(args.source)))
