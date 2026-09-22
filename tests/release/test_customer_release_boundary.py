"""Keep release validation and maintainer tools outside customer delivery."""

from pathlib import Path

import yaml

from scripts.release.validate_stable_release import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]


def test_release_web_tests_precede_build_and_packaging():
    workflow = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())
    steps = workflow['jobs']['web']['steps']
    test = next(i for i, step in enumerate(steps) if step.get('run') == 'npm test')
    build = next(i for i, step in enumerate(steps) if step.get('run') == 'npm run build')
    package = next(i for i, step in enumerate(steps) if step['name'] == 'Package Web client')
    assert test < build < package
    assert steps[test]['working-directory'] == 'clients/web'
    assert not steps[test].get('continue-on-error', False)


def test_local_harness_excluded_from_distribution_contexts():
    assert '/.automation/' in (ROOT / '.gitignore').read_text().splitlines()
    assert '.automation' in (ROOT / '.dockerignore').read_text().splitlines()
    assert '/.automation export-ignore' in (ROOT / '.gitattributes').read_text().splitlines()


def test_stable_inherits_rc_evidence_requirements(tmp_path):
    policy = {'gates': [{'id': 'G1', 'name': 'CI', 'type': 'internal',
                        'required_for': 'rc', 'evidence': 'ci.json'}]}
    rows, failed = evaluate_gates(policy, tmp_path, 'stable')
    assert failed
    assert rows[0]['required'] is True
    _, preview_failed = evaluate_gates(policy, tmp_path, 'preview')
    assert preview_failed is False


def test_release_assembly_fetches_and_requires_immutable_image_identity():
    workflow = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())
    steps = workflow['jobs']['assemble']['steps']
    download = next(step for step in steps if step.get('with', {}).get('name') == 'image-metadata')
    assert download['with']['path'] == 'release-assets/image-metadata'
    manifest = next(
        step['run'] for step in steps
        if step['name'] == 'Build checksums, manifest, then final checksums'
    )
    assert 'assert re.fullmatch' in manifest
    assert '--image-digest "$IMAGE_DIGEST"' in manifest
    assert '|| true' not in manifest
