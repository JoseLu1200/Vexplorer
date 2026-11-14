"""Resumable full-corpus preparation and paired public-only benchmark.

No reference is passed to the inference subprocess. Scores remain diagnostic:
official source splits and the adapter's family partitions are different axes.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

from tools.prepare_plankassembly import GENERATOR_VERSION, prepare_plankassembly

REPO = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def build_plan(source: Path, batch_size: int = 50) -> dict:
    if not 1 <= batch_size <= 50:
        raise ValueError('batch_size must be between 1 and 50')
    batches, counts, hashes, split_hashes = [], {}, {}, {}
    for split in ('valid', 'test', 'train'):
        path = source / 'extracted/data/splits' / f'{split}.txt'
        names = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        if len(names) != len(set(names)):
            raise ValueError(f'duplicate source entries in {split}')
        split_hashes[split] = digest(path)
        counts[split] = len(names)
        for name in names:
            if Path(name).name != name or not name.endswith('.json'):
                raise ValueError('unsafe source filename')
            if name not in hashes:
                hashes[name] = digest(source / 'extracted/data/model' / name)
        for offset in range(0, len(names), batch_size):
            batches.append({'key': f'{split}-{offset:06d}', 'split': split,
                            'offset': offset, 'count': min(batch_size, len(names) - offset)})
    return {'schema_version': 1, 'generator_version': GENERATOR_VERSION,
            'batch_size': batch_size, 'case_count': sum(counts.values()),
            'split_counts': counts, 'split_sha256': split_hashes,
            'source_sha256': hashes, 'batches': batches}


def verify_tree(root: Path) -> None:
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != expected:
            raise ValueError(f'integrity failure: {root.name}/{name}')


def prepare_batch(source: Path, root: Path, batch: dict) -> tuple[Path, Path]:
    public, private = root / 'public' / batch['key'], root / 'private' / batch['key']
    receipt = root / 'receipts' / f"{batch['key']}.json"
    if public.exists() != private.exists():
        quarantine = root / 'quarantine'
        quarantine.mkdir(exist_ok=True)
        for path in (public, private):
            if path.exists():
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('recovery target outside preparation root')
                path.rename(quarantine / f'{batch["key"]}-{path.parent.name}-{uuid4().hex}')
        receipt.unlink(missing_ok=True)
    if public.exists() and private.exists():
        verify_tree(public)
        verify_tree(private)
        manifest = json.loads((public / 'manifest.json').read_text())
        expected = (batch['split'], batch['offset'], batch['count'], GENERATOR_VERSION)
        actual = tuple(manifest[k] for k in ('source_split', 'source_offset', 'case_count', 'generator_version'))
        if actual != expected:
            raise ValueError('prepared batch differs from frozen plan')
    else:
        prepare_plankassembly(source, public, private, split=batch['split'],
                              offset=batch['offset'], limit=batch['count'])
    roots = {'public': digest(public / 'SHA256SUMS'), 'private': digest(private / 'SHA256SUMS')}
    if receipt.exists() and json.loads(receipt.read_text()) != roots:
        raise ValueError('prepared receipt integrity failure')
    if not receipt.exists():
        write_json(receipt, roots)
    return public, private


def select_attempt(batch_root: Path, *, retry_failed: bool) -> tuple[Path, bool]:
    attempts = sorted(p for p in batch_root.iterdir()
                      if p.is_dir() and re.fullmatch(r'attempt-\d+', p.name))
    completed = [(p, verify_frozen(p)) for p in attempts if (p / 'frozen-manifest.json').exists()]
    if completed:
        successful = [(p, frozen) for p, frozen in completed
                      if frozen['results'] and all(r['status'] == 'succeeded' for r in frozen['results'])]
        if successful:
            return max(successful, key=lambda item: int(item[0].name.split('-')[1]))[0], False
        latest, frozen = max(completed, key=lambda item: int(item[0].name.split('-')[1]))
        failed = any(r['status'] != 'succeeded' for r in frozen['results'])
        if not retry_failed or not failed:
            return latest, False
    ordinal = max((int(p.name.split('-')[1]) for p in attempts), default=0) + 1
    return batch_root / f'attempt-{ordinal:03d}', True


def ensure_space(root: Path, minimum_mb: int) -> None:
    if shutil.disk_usage(root).free < minimum_mb * 1024 * 1024:
        raise RuntimeError('insufficient free disk space for next batch')


def scoring_fingerprints() -> dict:
    paths = ('tools/build_panel_evaluation_references.py', 'evaluation/metrics.py')
    return {path: digest(REPO / path) for path in paths}


def verify_frozen(output: Path) -> dict:
    frozen = json.loads((output / 'frozen-manifest.json').read_text())
    for name, expected in frozen['files'].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output.resolve()) or not path.is_file() or digest(path) != expected:
            raise ValueError(f'frozen integrity failure: {name}')
    return frozen


def run_module(module: str, arguments: list[str], log: Path) -> None:
    with log.open('ab') as stream:
        subprocess.run([sys.executable, '-m', module, *arguments], cwd=REPO,
                       stdout=stream, stderr=subprocess.STDOUT, check=True)


def score_batch(root: Path, batch: dict, output: Path, *, prepared_root: Path | None = None,
                effective_date: str | None = None) -> dict:
    # Import evaluator only after the inference subprocess has frozen predictions.
    from tools.build_panel_evaluation_references import build_evaluator_references
    from evaluation.metrics import evaluate_files

    frozen = verify_frozen(output)
    raw = json.loads(((prepared_root or root) / 'private' / batch['key'] / 'references.json').read_text())
    reports = {}
    for phase in ('baseline', 'final'):
        prediction_path = output / f'{phase}-predictions.json'
        predictions = json.loads(prediction_path.read_text())
        reference_path = root / 'scores-private' / batch['key'] / f'{phase}.json'
        reference = build_evaluator_references(
            predictions, raw, prediction_sha256=digest(prediction_path),
            evidence_kind='development_diagnostic', effective_date=effective_date or date.today().isoformat(),
            round_digits=1, tolerance_mm=1.0, acceptable_scenario_key=None)
        write_json(reference_path, reference)
        reports[phase] = evaluate_files(prediction_path, reference_path, tolerance_mm=1.0)
    result = {'key': batch['key'], 'split': batch['split'], 'case_count': batch['count'],
              'selected_attempt': output.name,
              'succeeded': sum(r['status'] == 'succeeded' for r in frozen['results']),
              'frozen_sha256': digest(output / 'frozen-manifest.json'), 'reports': reports}
    write_json(root / 'scores' / f"{batch['key']}.json", result)
    return result


def summarize(results: list[dict], plan: dict) -> dict:
    summary = {'planned_cases': plan['case_count'],
               'evaluated_cases': sum(r['case_count'] for r in results),
               'succeeded_cases': sum(r['succeeded'] for r in results), 'by_source_split': {}}
    for split in plan['split_counts']:
        selected = [r for r in results if r['split'] == split]
        phases = {}
        for phase in ('baseline', 'final'):
            metrics = {}
            for metric in ('component_types', 'quantity_weighted'):
                counts = {key: sum(r['reports'][phase]['bom'][metric][key] for r in selected)
                          for key in ('true_positive', 'predicted', 'reference')}
                tp, predicted, reference = (counts[k] for k in ('true_positive', 'predicted', 'reference'))
                metrics[metric] = {**counts, 'precision': tp / predicted if predicted else None,
                                   'recall': tp / reference if reference else None,
                                   'f1': 2 * tp / (predicted + reference) if predicted + reference else None}
            phases[phase] = metrics
        summary['by_source_split'][split] = {'evaluated_cases': sum(r['case_count'] for r in selected),
                                             'planned_cases': plan['split_counts'][split], **phases}
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--provider', choices=('openai', 'codex-subscription'), default='codex-subscription')
    parser.add_argument('--prepared-root', type=Path)
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--minimum-free-mb', type=int, default=2048)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=2)
    parser.add_argument('--proposer-model', default='gpt-6.1-sol')
    parser.add_argument('--reviewer-model', default='gpt-6.1-sol')
    args = parser.parse_args(argv)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    prepared_root = (args.prepared_root or root).resolve()
    if args.minimum_free_mb < 0:
        parser.error('--minimum-free-mb must be non-negative')
    # Exclusive lock prevents two orchestrators from spending on the same cohort.
    lock = root / 'running.lock'
    with lock.open('x') as stream:
        stream.write(str(os.getpid()))
    preparation_lock = prepared_root / 'preparation.lock'
    preparation_locked = False
    try:
        prepared_root.mkdir(parents=True, exist_ok=True)
        if prepared_root != root and (prepared_root / 'running.lock').exists():
            raise RuntimeError('prepared root has an active or interrupted coordinator')
        with preparation_lock.open('x') as stream:
            stream.write(str(os.getpid()))
        preparation_locked = True
        plan = build_plan(args.source.resolve(), args.batch_size)
        configuration = {'proposer': args.proposer_model, 'reviewer': args.reviewer_model,
                         'workers': args.workers, 'provider': args.provider}
        from tools.run_general_benchmark import tracked_code_fingerprints
        plan['runtime_sha256'] = tracked_code_fingerprints()
        plan['orchestrator_sha256'] = digest(Path(__file__))
        plan['adapter_sha256'] = digest(REPO / 'tools/prepare_plankassembly.py')
        plan['scoring_sha256'] = scoring_fingerprints()
        plan['prepared_root'] = str(prepared_root)
        plan['configuration'] = configuration
        plan_path = root / 'plan-private.json'
        existing = json.loads(plan_path.read_text()) if plan_path.exists() else None
        plan['effective_date'] = existing['effective_date'] if existing else date.today().isoformat()
        if plan_path.exists():
            if existing != plan:
                raise ValueError('source, code or configuration changed; use a new output directory')
        else:
            write_json(plan_path, plan)
        for index, batch in enumerate(plan['batches']):
            ensure_space(root, args.minimum_free_mb)
            public, private = prepare_batch(args.source, prepared_root, batch)
            raw = json.loads((private / 'references.json').read_text())
            names = [line.strip() for line in (args.source / 'extracted/data/splits' / f"{batch['split']}.txt").read_text().splitlines() if line.strip()]
            selected = names[batch['offset']:batch['offset'] + batch['count']]
            if ([r['source_file'] for r in raw] != selected
                    or any(r['source_sha256'] != plan['source_sha256'][r['source_file']] for r in raw)):
                raise ValueError('prepared source differs from frozen selection')
            write_json(root / 'status.json', {'stage': 'preparing', 'prepared_batches': index + 1,
                                              'total_batches': len(plan['batches']), 'planned_cases': plan['case_count']})
            print(f"prepared {index + 1}/{len(plan['batches'])}: {batch['key']}", flush=True)
        write_json(root / 'status.json', {'stage': 'prepared', 'prepared_cases': plan['case_count']})
        if not args.live:
            return 0
        results = []
        for batch in plan['batches']:
            ensure_space(root, args.minimum_free_mb)
            if tracked_code_fingerprints() != plan['runtime_sha256']:
                raise RuntimeError('runtime changed during evaluation; use a new output directory')
            if scoring_fingerprints() != plan['scoring_sha256']:
                raise RuntimeError('evaluator changed during evaluation; use a new output directory')
            batch_root = root / 'runs' / batch['key']
            batch_root.mkdir(parents=True, exist_ok=True)
            output, run_needed = select_attempt(batch_root, retry_failed=args.retry_failed)
            if run_needed:
                write_json(root / 'status.json', {'stage': 'inference', 'batch': batch['key'],
                                                  'evaluated_cases': sum(r['case_count'] for r in results),
                                                  'planned_cases': plan['case_count']})
                run_module('tools.run_general_benchmark', [
                    '--input', str(prepared_root / 'public' / batch['key'] / 'agent_cases'),
                    '--output', str(output), '--dataset-id', f"plank-full-{batch['key']}",
                    '--strict-bundles', '--workers', str(args.workers),
                    '--proposer-model', args.proposer_model, '--reviewer-model', args.reviewer_model,
                    '--provider', args.provider,
                ], batch_root / f'{output.name}.log')
            result = score_batch(root, batch, output, prepared_root=prepared_root,
                                 effective_date=plan['effective_date'])
            results.append(result)
            write_json(root / 'summary.json', summarize(results, plan))
            print(f"evaluated {batch['key']}: {result['succeeded']}/{batch['count']}", flush=True)
            if not result['succeeded']:
                raise RuntimeError('batch has zero successful paired outcomes; stopped before spending on remaining corpus')
        write_json(root / 'status.json', {'stage': 'complete', **summarize(results, plan)})
        return 0
    except Exception as exc:
        write_json(root / 'error.json', {'type': type(exc).__name__, 'message': str(exc)[:500]})
        write_json(root / 'status.json', {'stage': 'stopped', 'error_file': 'error.json'})
        raise
    finally:
        if preparation_locked:
            preparation_lock.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
