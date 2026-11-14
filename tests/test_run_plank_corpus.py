import json
from pathlib import Path

import pytest

from tools.run_plank_corpus import build_plan, verify_tree, prepare_batch, score_batch, summarize, digest, select_attempt
from test_prepare_plankassembly import _write_fixture


def test_plan_covers_every_split_without_truncation(tmp_path: Path):
    _write_fixture(tmp_path)
    splits = tmp_path / 'extracted/data/splits'
    (splits / 'train.txt').write_text('fixture_normal.json\n')
    (splits / 'test.txt').write_text('fixture_missing_normal.json\n')
    plan = build_plan(tmp_path, batch_size=1)
    assert plan['case_count'] == 4
    assert plan['split_counts'] == {'valid': 2, 'test': 1, 'train': 1}
    assert len({batch['key'] for batch in plan['batches']}) == 4
    assert [b['offset'] for b in plan['batches'] if b['split'] == 'valid'] == [0, 1]
    assert len(plan['source_sha256']) == 2


def test_batch_resume_verifies_integrity(tmp_path: Path):
    source = tmp_path / 'source'
    _write_fixture(source)
    batch = {'key': 'valid-000000', 'split': 'valid', 'offset': 0, 'count': 2}
    public, private = prepare_batch(source, tmp_path / 'run', batch)
    assert prepare_batch(source, tmp_path / 'run', batch) == (public, private)
    verify_tree(public)
    assert len(json.loads((private / 'references.json').read_text())) == 2
    (public / 'agent_cases/plank-001.zip').write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='integrity'):
        prepare_batch(source, tmp_path / 'run', batch)


def test_resume_recovers_one_sided_preparation(tmp_path: Path):
    source, root = tmp_path / 'source', tmp_path / 'run'
    _write_fixture(source)
    batch = {'key': 'valid-000000', 'split': 'valid', 'offset': 0, 'count': 2}
    public, private = prepare_batch(source, root, batch)
    private.rename(private.with_name('old-private'))
    recovered_public, recovered_private = prepare_batch(source, root, batch)
    verify_tree(recovered_public)
    verify_tree(recovered_private)
    assert list((root / 'quarantine').iterdir())


def test_retry_preserves_failed_attempt_and_selects_latest_success(tmp_path: Path):
    first = tmp_path / 'attempt-001'
    first.mkdir()
    (first / 'frozen-manifest.json').write_text(json.dumps({'files': {}, 'results': [{'status': 'failed_before_baseline'}]}))
    (tmp_path / 'attempt-001.log').write_text('log')
    assert select_attempt(tmp_path, retry_failed=False) == (first, False)
    second = tmp_path / 'attempt-002'
    assert select_attempt(tmp_path, retry_failed=True) == (second, True)
    second.mkdir()
    (second / 'frozen-manifest.json').write_text(json.dumps({'files': {}, 'results': [{'status': 'succeeded'}]}))
    assert select_attempt(tmp_path, retry_failed=False) == (second, False)
    third = tmp_path / 'attempt-003'
    third.mkdir()
    (third / 'frozen-manifest.json').write_text(json.dumps({'files': {}, 'results': [{'status': 'failed_before_baseline'}]}))
    assert select_attempt(tmp_path, retry_failed=False) == (second, False)


def test_plan_rejects_invalid_size_and_missing_model(tmp_path: Path):
    _write_fixture(tmp_path)
    with pytest.raises(ValueError, match='batch_size'):
        build_plan(tmp_path, batch_size=51)
    (tmp_path / 'extracted/data/splits/test.txt').write_text('missing.json\n')
    (tmp_path / 'extracted/data/splits/train.txt').write_text('fixture_normal.json\n')
    with pytest.raises(FileNotFoundError):
        build_plan(tmp_path)


def test_failed_predictions_remain_in_scoring_denominator(tmp_path: Path):
    source, root = tmp_path / 'source', tmp_path / 'run'
    _write_fixture(source)
    batch = {'key': 'valid-000000', 'split': 'valid', 'offset': 0, 'count': 2}
    prepare_batch(source, root, batch)
    output = root / 'runs/valid-000000/attempt-001'
    output.mkdir(parents=True)
    predictions = {'schema_version': '1.0', 'dataset_id': 'fixture', 'cases': [
        {'id': f'plank-{i:03d}', 'components': [], 'retrieved_item_ids': None,
         'cost': None, 'hours': None, 'assisted': None, 'scenarios': []} for i in (1, 2)]}
    hashes = {}
    for phase in ('baseline', 'final'):
        path = output / f'{phase}-predictions.json'
        path.write_text(json.dumps(predictions))
        hashes[path.name] = digest(path)
    (output / 'frozen-manifest.json').write_text(json.dumps({
        'files': hashes, 'results': [{'status': 'failed_before_baseline'}] * 2}))
    result = score_batch(root, batch, output)
    assert result['succeeded'] == 0
    report = result['reports']['final']['bom']['component_types']
    assert report['reference'] == 4
    assert report['true_positive'] == 0
    summary = summarize([result], {'case_count': 100, 'split_counts': {'valid': 100}})
    assert summary['evaluated_cases'] == 2
    assert summary['by_source_split']['valid']['final']['component_types']['recall'] == 0
    (output / 'baseline-predictions.json').write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        score_batch(root, batch, output)
