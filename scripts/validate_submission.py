"""Validate local submission evidence, or additionally check the deployed service.

Use --predeploy to check everything recorded locally while allowing a pending deploy_url.
This cannot verify class sign-up uniqueness, real identities, or GitHub grader permissions.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from scripts.sample_queries import SAMPLES


def validate_local(root: Path, predeploy: bool = False) -> list[str]:
    errors = []
    for file in ('app.py', 'pyproject.toml', 'uv.lock', 'README.md', 'submission.json'):
        if not (root / file).is_file():
            errors.append(f'Missing required root file: {file}')
    if errors:
        return errors
    try:
        data = json.loads((root / 'submission.json').read_text())
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
    except (ValueError, OSError) as exc:
        return [f'Invalid submission.json: {exc}']
    if data.get('path') != 'research':
        errors.append('Expected path=research')
    authors = data.get('authors')
    if (not isinstance(authors, list) or len(authors) < 3
            or not all(isinstance(author, str) and author.strip() for author in authors)):
        errors.append('authors must contain every team member (at least three in this repository)')
    elif len(set(authors)) != len(authors):
        errors.append('authors contains duplicate entries')
    if not predeploy:
        url = data.get('deploy_url', '')
        parsed = urlparse(url) if isinstance(url, str) else None
        if (not parsed or parsed.scheme != 'https' or not parsed.netloc
                or any(s in url.upper() for s in ('REPLACE', 'YOUR-', 'EXAMPLE'))):
            errors.append('Set deploy_url to the actual Cloud Run HTTPS URL; placeholder is not a valid submission.')
    readme = (root / 'README.md').read_text()
    start, end = '<!-- SAMPLE_RESULTS_START -->', '<!-- SAMPLE_RESULTS_END -->'
    if start not in readme or end not in readme or 'Not yet recorded.' in readme:
        errors.append('Required real sample comparisons are not recorded in README. Run scripts.compare_samples --write-readme.')
    from scripts.compare_samples import reference_matches, answer_matches
    models = set()
    for sample in SAMPLES:
        path = root / 'artifacts' / 'samples' / f"{sample['id']}.json"
        if not path.is_file():
            errors.append(f'Missing recorded comparison: {path.relative_to(root)}')
            continue
        try:
            record = json.loads(path.read_text())
            if record['id'] != sample['id'] or record['question'] != sample['question']:
                raise ValueError('Sample identity or question differs from the documented sample')
            model = record['model']
            if not isinstance(model, str) or not model.strip():
                raise ValueError('Model identifier is missing')
            models.add(model)
            if datetime.fromisoformat(record['recorded_at']).tzinfo is None:
                raise ValueError('Recording timestamp needs a timezone')
            if not isinstance(record['baseline'], str) or not record['baseline'].strip():
                raise ValueError('No-tools/no-system baseline answer is empty')
            reference = record['reference']
            if not reference['ok'] or not reference['rows'] or reference['sql'] != sample['sql']:
                raise ValueError('Reference SQL/results are missing or differ from the sample')
            dataset = record['dataset']
            for source in ('lca', 'uscis', 'perm'):
                if not dataset[source] or not all(file['bytes'] > 0 and len(file['sha256']) == 64 for file in dataset[source]):
                    raise ValueError(f'Missing dataset fingerprint for {source}')
            agent = record['agent']
            if not agent['response'].strip():
                raise ValueError('Agent answer is empty')
            results = [json.loads(call['result']) for call in agent['tool_calls']
                       if call.get('agent') == 'researcher-' + sample['source'] and call.get('name') == 'run_sql']
            results = [result for result in results if result.get('ok')]
            if not results or not reference_matches(reference, results):
                raise ValueError('Expected reference values not found in successful source queries; inspect and rerun the agent')
            if not answer_matches(reference, agent['response']):
                raise ValueError('Expected reference values are absent from final answer tables')
            if sample['id'] not in readme:
                raise ValueError('Recorded sample is not included in README')
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            errors.append(f"Invalid comparison {sample['id']}: {exc}")
    if len(models) > 1:
        errors.append('Recorded comparisons use different model identifiers; rerun them with one model')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--online', action='store_true')
    mode.add_argument('--predeploy', action='store_true')
    args = parser.parse_args()
    errors = validate_local(Path.cwd(), predeploy=args.predeploy)
    if errors:
        raise SystemExit('\n'.join('- ' + error for error in errors))
    if args.online:
        import httpx
        data = json.loads(Path('submission.json').read_text())
        url = data['deploy_url'].rstrip('/')
        with httpx.Client(timeout=300) as client:
            status = client.get(url + '/api/status')
            status.raise_for_status()
            state = status.json()
            if state.get('demo') or state.get('missing_sources') or {s['name'] for s in state['sources']} != {'lca', 'uscis', 'perm'}:
                raise SystemExit(f'Deployed real sources are incomplete: {state}')
            response = client.post(url + '/chat', json={'message': 'I want a job with good visa sponsorship prospects'})
            response.raise_for_status()
            result = response.json()
            if not {'response', 'session_id', 'tool_calls'} <= result.keys():
                raise SystemExit('Invalid /chat response shape')
            plans = [json.loads(c['result']) for c in result['tool_calls'] if c['agent'] == 'lead' and c['name'] == 'plan']
            if not plans or plans[0].get('action') != 'clarify':
                raise SystemExit('Live vague-query clarification failed. Inspect model configuration and trace.')
    print('Local evidence checks passed. Still review SQL scope, class sign-up uniqueness, author identities and grader permissions.')
    if args.predeploy:
        print('Deployment URL and live service availability were intentionally not checked.')


if __name__ == '__main__':
    main()
