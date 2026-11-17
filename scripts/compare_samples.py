"""Generate real sample answers, reference results and no-tools baselines; never fabricates results.

uv run python -m scripts.compare_samples --write-readme
Requires local/Cloud Shell ADC for Vertex AI, and the three real data files (or SPONSOR_GCS_URI).
Can call a deployed agent using --url; reference SQL and baseline still run in this process.
"""
import argparse
import asyncio
import json
import os
import hashlib
import math
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from scripts.sample_queries import SAMPLES


def fence(text, language=''):
    ticks = '```'
    while ticks in text:
        ticks += '`'
    return f'{ticks}{language}\n{text}\n{ticks}'


def reference_matches(reference: dict, results: list[dict]) -> bool:
    """Check expected row values against tool results, allowing extra columns/alias differences.

    This checks values, not whether the model chose semantically correct filters.
    """
    def equal(left, right):
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return math.isclose(left, right, rel_tol=1e-7, abs_tol=1e-7)
        if isinstance(left, (int, float)) and isinstance(right, str):
            try:
                return math.isclose(left, float(Decimal(right)), rel_tol=1e-7, abs_tol=1e-7)
            except (InvalidOperation, ValueError, OverflowError):
                return False
        return left == right

    def contains(expected, actual):
        remaining = list(actual)
        for value in expected:
            index = next((i for i, candidate in enumerate(remaining) if equal(value, candidate)), None)
            if index is None:
                return False
            remaining.pop(index)
        return True

    return any(all(any(contains(row, actual) for actual in result.get('rows', []))
                       for row in reference['rows']) for result in results)


def answer_matches(reference: dict, answer: str) -> bool:
    """Check the final rendered tables too; a correct hidden query alone is insufficient."""
    rows = [[cell.strip() for cell in line.strip().split('|')[1:-1]]
            for line in answer.splitlines() if line.strip().startswith('|') and line.strip().endswith('|')]
    return reference_matches(reference, [{'rows': rows}])


def dataset_manifest(sources):
    manifest = {}
    for name, source in sources.items():
        manifest[name] = []
        for path in source.tables.values():
            file = Path(path)
            with file.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            manifest[name].append({'file': file.name, 'bytes': file.stat().st_size, 'sha256': digest})
    return manifest


def format_readme(records, model):
    blocks = ['<!-- SAMPLE_RESULTS_START -->', '### Recorded model comparisons', '',
              f'Actual calls using `{model}`. Baseline: one user message, no tools, no system prompt.', '']
    for record in records:
        blocks += [f"#### {record['id']}", '', record['question'], '',
                   '**Expected answer (executed reference SQL):**', '',
                   fence(json.dumps(record['reference'], indent=2, ensure_ascii=False, default=str), 'json'), '',
                   '**Agent answer:**', '', record['agent']['response'], '',
                   f"Reference values found in source query results: **{record['reference_values_match']}**; in final tables: **{record['answer_values_match']}**. Review SQL scope separately.", '',
                   '**Same-model answer without tools or system prompt:**', '',
                   fence(record['baseline']), '',
                   f"Full tool trace: [artifacts/samples/{record['id']}.json](artifacts/samples/{record['id']}.json)", '']
    return '\n'.join(blocks + ['<!-- SAMPLE_RESULTS_END -->'])


async def run(args):
    # One model for all three roles and the baseline, as required by the assignment.
    for role in ('LEAD', 'RESEARCHER', 'WRITER'):
        os.environ[f'SPONSOR_{role}_MODEL'] = args.model
    from agents import lead, llm
    from server.main import REQUEST_BUDGET_SECONDS
    from sources import active_sources
    from sources.remote import sync_from_gcs
    await asyncio.to_thread(sync_from_gcs)
    sources = active_sources()
    if not {'lca', 'uscis', 'perm'} <= sources.keys():
        raise RuntimeError('All three real sources are required. Configure SPONSOR_GCS_URI or data/clean; toy results cannot be submitted.')
    out = Path('artifacts/samples')
    out.mkdir(parents=True, exist_ok=True)
    records = []
    manifest = dataset_manifest(sources)
    for sample in SAMPLES:
        reference = await asyncio.to_thread(sources[sample['source']].run_sql, sample['sql'])
        if not reference['ok'] or not reference['rows']:
            raise RuntimeError(f"{sample['id']}: reference SQL failed or returned no rows: {reference}")
        if args.url:
            import httpx
            async with httpx.AsyncClient(timeout=300) as client:
                status = await client.get(args.url.rstrip('/') + '/api/status')
                status.raise_for_status()
                if set(status.json().get('models', {}).values()) != {args.model}:
                    raise RuntimeError('Deployed model differs from requested baseline model')
                response = await client.post(args.url.rstrip('/') + '/chat', json={'message': sample['question']})
                response.raise_for_status()
                agent = response.json()
        else:
            response, calls = await asyncio.wait_for(lead.run(sample['question'], []), timeout=REQUEST_BUDGET_SECONDS)
            agent = {'response': response, 'tool_calls': calls}
        successful = []
        for call in agent['tool_calls']:
            if call.get('agent') == 'researcher-' + sample['source'] and call.get('name') == 'run_sql':
                result = json.loads(call['result'])
                if result.get('ok'):
                    successful.append(result)
        if not successful:
            raise RuntimeError(f"{sample['id']}: agent produced no successful query trace; inspect configuration/model before submitting")
        baseline = await llm.complete([{'role': 'user', 'content': sample['question']}], role='researcher')
        if not isinstance(baseline.get('content'), str) or not baseline['content'].strip():
            raise RuntimeError(f"{sample['id']}: no-tools baseline returned an empty answer")
        record = {**sample, 'model': args.model, 'recorded_at': datetime.now(timezone.utc).isoformat(),
                  'reference': reference, 'agent': agent, 'baseline': baseline.get('content') or '',
                  'dataset': manifest, 'reference_values_match': reference_matches(reference, successful),
                  'answer_values_match': answer_matches(reference, agent['response'])}
        (out / f"{sample['id']}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str) + '\n')
        records.append(record)
        print(f"Recorded {sample['id']}; query values match={record['reference_values_match']}; answer values match={record['answer_values_match']}", flush=True)
    text = format_readme(records, args.model)
    (out / 'comparisons.md').write_text(text + '\n')
    if args.write_readme:
        readme = Path('README.md')
        original = readme.read_text()
        start, end = '<!-- SAMPLE_RESULTS_START -->', '<!-- SAMPLE_RESULTS_END -->'
        if start not in original or end not in original:
            raise RuntimeError('README sample markers missing')
        before, rest = original.split(start, 1)
        _, after = rest.split(end, 1)
        readme.write_text(before + text + after)
    print('Review numerical agreement against reference SQL before submitting. No automated semantic correctness claim is made.')
    mismatches = [record['id'] for record in records if not record['reference_values_match'] or not record['answer_values_match']]
    if mismatches:
        raise RuntimeError(f'Recorded actual answers, but reference values did not match: {mismatches}. Inspect traces before submitting.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', help='Optional deployed /chat host; omit to run current local code')
    parser.add_argument('--model', default=os.environ.get('SPONSOR_MODEL', 'vertex_ai/gemini-3.5-flash-lite'))
    parser.add_argument('--write-readme', action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
