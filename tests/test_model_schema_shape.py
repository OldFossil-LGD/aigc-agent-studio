"""The gate must accept only the CLI schema shape.

Measured on the real platform: `libtv model <key>` yields {schema: {...}} while the
MCP channel yields {inputContract: {...}}. They are different objects, so feeding
an MCP contract to the gate must be refused loudly instead of half-parsed.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts' / 'libtv_model_rules_gate.py'

CLI_SHAPED = {"modelKey": "demo", "modelName": "Demo", "modality": "video",
              "schema": {"properties": {"modeType": {"items": {"t2v": [1, 5]}}},
                         "rules": [{"require": ["prompt"]}]}}
MCP_SHAPED = {"ok": True, "modelKey": "demo",
              "inputContract": {"model": "demo", "modality": "video",
                                "promptSchema": {"maxLength": 11000, "type": "string"},
                                "parameterSchemas": {"generate": {"anyOf": []}}}}


def run(payload):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'schema.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = subprocess.run([sys.executable, str(GATE), '--schema', str(path),
                                 '--prompt', 'a cat'],
                                capture_output=True, text=True, encoding='utf-8',
                                cwd=str(ROOT), timeout=120)
    try:
        body = json.loads(result.stdout)
    except ValueError:
        body = {}
    return result.returncode, body


class SchemaShapeTests(unittest.TestCase):
    def test_cli_shape_is_accepted(self):
        code, body = run(CLI_SHAPED)
        self.assertNotEqual(body.get('verdict'), 'no_schema', body)
        self.assertEqual(code, 0, body)

    def test_mcp_contract_is_refused(self):
        code, body = run(MCP_SHAPED)
        self.assertEqual(body.get('verdict'), 'no_schema', body)
        self.assertEqual(code, 4, body)

    def test_unrun_layers_are_not_reported_as_passed(self):
        _, body = run(CLI_SHAPED)
        layers = body.get('layers') or {}
        self.assertEqual(layers.get('ranges', {}).get('state'), 'skipped')
        self.assertIn('≠ 通过', layers.get('ranges', {}).get('detail', ''))


if __name__ == '__main__':
    unittest.main()
