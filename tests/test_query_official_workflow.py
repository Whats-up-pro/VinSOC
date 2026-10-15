"""The full official inventory needs a manual, long-running, scope-bound entrypoint."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/query-official-experiments.yml'


def test_full_query_experiments_have_a_manual_scope_bound_entrypoint():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    assert not re.search(r'^  (push|pull_request|schedule|workflow_run):', text, re.M)
    assert 'options: [evaluation, pipeline]' in text
    assert 'VINSOC_EXPECTED_SCOPE: ${{ inputs.scope }}' in text
    assert "request['scope'] != os.environ['VINSOC_EXPECTED_SCOPE']" in text
    assert 'OFFICIAL_SCOPE_MISMATCH' in text
    assert text.index('OFFICIAL_SCOPE_MISMATCH') < text.index('Install SDK')
    assert "if: github.ref == 'refs/heads/master'" in text
    timeout = int(re.search(r'timeout-minutes: (\d+)', text).group(1))
    assert 120 <= timeout <= 360


def test_official_entrypoint_keeps_the_calibrated_runtime_steps_and_checkpoints():
    text = WORKFLOW.read_text(encoding='utf-8')
    original = (ROOT / '.github/workflows/query-live-ui.yml').read_text(encoding='utf-8')
    start = '      - name: Install SDK and Linux isolation backend\n'
    assert text[text.index(start):] == original[original.index(start):]
    assert 'inputs.mode' in text and 'options: [preflight, live]' in text
    assert 'cancel-in-progress: false' in text
    assert 'if: always()' in text
