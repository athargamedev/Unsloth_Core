import json
import subprocess
import sys
from pathlib import Path


def test_new_npc_bootstrap_json(tmp_path):
    script = Path('/home/athar/Projects/Unsloth_Core/src/cli/ucore')
    cmd = [sys.executable, str(script), 'new-npc-bootstrap', 'test_npc', '--json', '--skip-spec']
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload['npc_key'] == 'test_npc'
    assert '.pipeline/runs/<run_id>/artifacts.json' in payload['json_issue_policy']['rule']
    assert 'compare-local-models' in payload['steps'][1]
