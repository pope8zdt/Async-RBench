"""Local, aggregate-only submissions and separate repository-maintainer reviews.

Validation proves consistency and content integrity, never authenticity of scores
or reviewer identity. Repository review permissions are the publication boundary.
This module and its check command require only the Python standard library.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean
from urllib.parse import urlsplit

from .main_experiment import load_main_cohort

COHORT_FIELDS = {'id', 'case_count', 'selection_sha256', 'repetitions', 'theme_counts'}
ENVELOPE_FIELDS = {'schemaVersion', 'submissionId', 'contentSha256', 'cohort',
                   'benchmarkCommit', 'configSha256', 'record'}
RECORD_FIELDS = {'model', 'version', 'scope', 'caseCount', 'completedCases', 'episodes', 'scored',
                 'linear', 'async', 'drs', 'observedLinear', 'observedAsync', 'observedDrs',
                 'pairedComplete', 'themeCount', 'themeScores', 'published', 'sourceSha256', 'date',
                 'coverageStatus', 'executionStatus', 'reviewStatus'}
OPTIONAL_RECORD_FIELDS = {'themeMetrics', 'resources'}
REVIEW_FIELDS = {'schemaVersion', 'submissionId', 'contentSha256', 'reviewStatus',
                 'reviewer', 'reviewedAt', 'evidenceUrl'}
REVIEW_STATUSES = ('materials_reviewed', 'independently_reproduced')


def _object(value, required, optional=frozenset(), label='object'):
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ValueError('Unexpected or missing fields in ' + label)


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid counter: ' + label)


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Invalid text: ' + label)


def _digest(value, length=64):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None:
        raise ValueError('Expected a lowercase hexadecimal digest')


def _number(value, *, maximum=1):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError('Expected a finite numeric metric in range')


def _same_metric(actual, expected):
    if expected is None:
        if actual is not None:
            raise ValueError('Metric must be null without complete coverage')
    else:
        _number(actual)
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('Inconsistent aggregate metric')


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Expected an ISO timestamp')
    try:
        timestamp = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Expected an ISO timestamp') from exc
    if timestamp.utcoffset() is None:
        raise ValueError('Timestamp requires a timezone')


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Submission is not finite JSON') from exc


def _identity(package):
    return hashlib.sha256(_canonical({k: v for k, v in package.items() if k not in ('submissionId', 'contentSha256')})).hexdigest()


def validate_submission(package, cohort) -> None:
    """Reject unknown fields, altered content, and inconsistent main-47 aggregates."""
    _object(package, ENVELOPE_FIELDS, label='submission')
    _integer(package['schemaVersion'], 1, 1, 'schemaVersion')
    _object(package['cohort'], COHORT_FIELDS, label='cohort')
    expected_cohort = {k: cohort[k] for k in COHORT_FIELDS}
    if _canonical(package['cohort']) != _canonical(expected_cohort) or cohort['case_count'] != 47 or cohort['repetitions'] != 3:
        raise ValueError('Submission does not match the fixed main-47 cohort')
    _digest(package['benchmarkCommit'], 40)
    if package['configSha256'] is not None:
        _digest(package['configSha256'])
    for key in ['submissionId', 'contentSha256']:
        _digest(package[key])
        if package[key] != _identity(package):
            raise ValueError('Submission content digest mismatch')
    validate_record(package['record'], cohort)


def validate_record(record, cohort) -> None:
    """Check self-reported aggregate consistency, without authenticating scores."""
    _object(record, RECORD_FIELDS, OPTIONAL_RECORD_FIELDS, 'record')
    _text(record['model'], 'model')
    if record['version'] != cohort['evaluation_contract_version'] or record['scope'] != 'main_experiment_47':
        raise ValueError('Incompatible scoring contract or experiment scope')
    _digest(record['sourceSha256'])
    if record['date'] is not None:
        _timestamp(record['date'])
    for field, low, high in [('caseCount', 47, 47), ('completedCases', 0, 47), ('episodes', 282, 282), ('scored', 0, 282), ('themeCount', 0, 8)]:
        _integer(record[field], low, high, field)
    completed = record['completedCases']
    full = completed == 47
    if record['pairedComplete'] is not full or record['published'] is not False:
        raise ValueError('Self-submissions cannot claim publication or inconsistent coverage')
    if (record['coverageStatus'] != ('complete' if full else 'incomplete')
            or record['executionStatus'] != 'unknown' or record['reviewStatus'] != 'self_reported'):
        raise ValueError('Invalid self-reported status')
    if record['scored'] < completed * 6:
        raise ValueError('Too few scored episodes for completed pairs')
    for official, observed in [('linear', 'observedLinear'), ('async', 'observedAsync'), ('drs', 'observedDrs')]:
        if completed:
            _number(record[observed])
        elif record[observed] is not None:
            raise ValueError('Observed metric must be null without complete cases')
        _same_metric(record[official], record[observed] if full else None)
    themes = record['themeScores']
    if not isinstance(themes, dict) or themes.keys() - cohort['theme_counts'].keys():
        raise ValueError('Unknown theme')
    if (len(themes) != record['themeCount'] or len(themes) > completed
            or sum(cohort['theme_counts'][t] for t in themes) < completed):
        raise ValueError('Inconsistent theme coverage')
    for score in themes.values():
        _number(score)
    _same_metric(record['observedDrs'], mean(themes.values()) if themes else None)
    if 'themeMetrics' in record:
        metrics = record['themeMetrics']
        _object(metrics, set(cohort['theme_counts']), label='themeMetrics')
        complete_total = 0
        metric_values = {key: [] for key in ['linear', 'async', 'drs']}
        for theme, counts in cohort['theme_counts'].items():
            detail = metrics[theme]
            _object(detail, {'linear', 'async', 'drs', 'caseCount', 'completedCases'}, label='theme metric')
            _integer(detail['caseCount'], counts, counts, 'theme caseCount')
            _integer(detail['completedCases'], 0, counts, 'theme completedCases')
            complete_total += detail['completedCases']
            if bool(detail['completedCases']) != (theme in themes):
                raise ValueError('Theme membership differs between metrics')
            for key in metric_values:
                if detail['completedCases']:
                    _number(detail[key])
                    metric_values[key].append(detail[key])
                elif detail[key] is not None:
                    raise ValueError('Empty theme metric must be null')
            if theme in themes:
                _same_metric(detail['drs'], themes[theme])
        if complete_total != completed:
            raise ValueError('Theme coverage does not sum to completed cases')
        for key, observed in [('linear', 'observedLinear'), ('async', 'observedAsync'), ('drs', 'observedDrs')]:
            _same_metric(record[observed], mean(metric_values[key]) if metric_values[key] else None)
    if 'resources' in record:
        _object(record['resources'], {'linear', 'async'}, label='resources')
        for mode in record['resources'].values():
            _object(mode, {'tokens', 'durationMs'}, label='resource mode')
            for resource in mode.values():
                _object(resource, {'mean', 'measuredEpisodes'}, label='resource metric')
                _integer(resource['measuredEpisodes'], 0, completed * 3, 'measuredEpisodes')
                if resource['measuredEpisodes']:
                    _number(resource['mean'], maximum=None)
                elif resource['mean'] is not None:
                    raise ValueError('Resource mean must be null without measurements')


def package_run(root, manifest_path, *, benchmark_commit, config_path=None) -> dict:
    """Package one declared run. Only allowlisted aggregates and hashes leave it."""
    from .main_results import export
    root, manifest_path = Path(root).resolve(), Path(manifest_path).resolve()
    _digest(benchmark_commit, 40)
    cohort = load_main_cohort(root)
    snapshot = export(root, manifest_path)
    if len(snapshot['records']) != 1:
        raise ValueError('Submission packaging requires exactly one declared run')
    source = snapshot['records'][0]
    record = {k: source[k] for k in RECORD_FIELDS | OPTIONAL_RECORD_FIELDS if k in source}
    record.update(published=False, coverageStatus='complete' if source['pairedComplete'] else 'incomplete',
                  executionStatus='unknown', reviewStatus='self_reported')
    package = {'schemaVersion': 1, 'cohort': {k: cohort[k] for k in COHORT_FIELDS},
               'benchmarkCommit': benchmark_commit,
               'configSha256': hashlib.sha256(Path(config_path).read_bytes()).hexdigest() if config_path is not None else None,
               'record': record}
    package['submissionId'] = package['contentSha256'] = _identity(package)
    validate_submission(package, cohort)
    return package


def _read(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON object field: ' + key)
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)


def validate_review(review, package):
    """Validate a maintainer assertion; this is not a cryptographic signature."""
    _object(review, REVIEW_FIELDS, label='review')
    _integer(review['schemaVersion'], 1, 1, 'review schemaVersion')
    for key in ['submissionId', 'contentSha256']:
        _digest(review[key])
        if review[key] != package[key]:
            raise ValueError('Review does not bind to this submission content')
    if review['reviewStatus'] not in REVIEW_STATUSES:
        raise ValueError('Unknown maintainer review status')
    _text(review['reviewer'], 'reviewer')
    _timestamp(review['reviewedAt'])
    evidence = review['evidenceUrl']
    if evidence is not None:
        if not isinstance(evidence, str) or len(evidence) > 2000 or any(c.isspace() or ord(c) < 32 for c in evidence):
            raise ValueError('Invalid public evidence URL')
        url = urlsplit(evidence)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or '\\' in evidence:
            raise ValueError('Evidence must be a public HTTPS reference without credentials')
    if review['reviewStatus'] == 'independently_reproduced' and evidence is None:
        raise ValueError('Independent reproduction requires a supporting evidence URL')


def _stored_json(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Submission directories must not be symlinks')
    for path in sorted(directory.glob('*.json')):
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError('Submission file escapes its directory')
        yield path, _read(path)


def _catalog(root):
    root = Path(root).resolve()
    if (root / 'submissions').is_symlink():
        raise ValueError('Submission directory must not be a symlink')
    cohort = load_main_cohort(root)
    packages, reviews = {}, {}
    for path, package in _stored_json(root / 'submissions/entries'):
        validate_submission(package, cohort)
        identity = package['submissionId']
        if identity in packages or path.name != identity + '.json':
            raise ValueError('Duplicate submission or filename does not match its digest')
        packages[identity] = package
    for path, review in _stored_json(root / 'submissions/reviews'):
        _object(review, REVIEW_FIELDS, label='review')
        identity = review['submissionId']
        _digest(identity)
        if identity not in packages:
            raise ValueError('Review refers to an unknown submission')
        if identity in reviews or path.name != identity + '.json':
            raise ValueError('Duplicate review or filename does not match its submission')
        validate_review(review, packages[identity])
        reviews[identity] = review
    return packages, reviews


def load_accepted(root) -> list[dict]:
    """Return only complete records with a separate, matching maintainer review."""
    packages, reviews = _catalog(root)
    records = []
    for identity, package in packages.items():
        if identity not in reviews or package['record']['pairedComplete'] is not True:
            continue
        review = reviews[identity]
        records.append({**package['record'], 'id': identity, 'submissionId': identity,
                        'reviewStatus': review['reviewStatus'], 'published': True,
                        'benchmarkCommit': package['benchmarkCommit'], 'configSha256': package['configSha256'],
                        'reviewer': review['reviewer'], 'reviewedAt': review['reviewedAt'],
                        'executionStatus': 'unknown', 'reviewEvidenceUrl': review['evidenceUrl']})
    return records


def _write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ['package', 'validate', 'review', 'check']:
        p = commands.add_parser(command)
        p.add_argument('--root', type=Path, default=Path.cwd())
        if command in ['validate', 'review']:
            p.add_argument('--input', type=Path, required=True)
        if command == 'package':
            p.add_argument('--manifest', type=Path, required=True)
            p.add_argument('--benchmark-commit', required=True)
            p.add_argument('--config', type=Path)
            p.add_argument('--output', type=Path, help='Defaults to submissions/entries/<digest>.json')
        if command == 'review':
            p.add_argument('--status', choices=REVIEW_STATUSES, required=True)
            p.add_argument('--reviewer', required=True)
            p.add_argument('--evidence-url')
            p.add_argument('--output', type=Path, help='Defaults to submissions/reviews/<digest>.json')
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == 'package':
            package = package_run(root, args.manifest, benchmark_commit=args.benchmark_commit, config_path=args.config)
            output = args.output or root / 'submissions/entries' / (package['submissionId'] + '.json')
            _write_new(output, package)
            result = {'submissionId': package['submissionId'], 'completedCases': package['record']['completedCases']}
        elif args.command in ['validate', 'review']:
            package = _read(args.input)
            validate_submission(package, load_main_cohort(root))
            if args.command == 'review':
                review = {'schemaVersion': 1, 'submissionId': package['submissionId'], 'contentSha256': package['contentSha256'],
                          'reviewStatus': args.status, 'reviewer': args.reviewer,
                          'reviewedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'evidenceUrl': args.evidence_url}
                validate_review(review, package)
                output = args.output or root / 'submissions/reviews' / (package['submissionId'] + '.json')
                _write_new(output, review)
            result = {'submissionId': package['submissionId'], 'valid': True}
        else:
            packages, reviews = _catalog(root)
            result = {'submissions': len(packages), 'reviews': len(reviews),
                      'accepted': sum(identity in reviews and package['record']['pairedComplete'] for identity, package in packages.items())}
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, 'Submission validation failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
