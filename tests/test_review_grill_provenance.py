"""Contract continuation and ledger projection preserve decision authority."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_intent_delivery import grill_gate_for
from scripts.compile_production import _grill_gate
from scripts.grill_ledger import gate, ledger_from_contract
from scripts.grill_session import (
    GrillSessionError, compile_contract, export_ledger, inherit_contract,
    load_session, new_session, save_session, skip, validate_contract,
)
from tests.test_grill_session import papercut_session


class ContractProvenanceTests(unittest.TestCase):
    def test_continue_preserves_proposals_defaults_and_user_locks(self):
        source = papercut_session()
        skip(source, 'G06', {'style_id': 'ink', 'register': 'stylized'})
        skip(source, 'I17')
        contract = compile_contract(source)
        self.assertEqual(validate_contract(contract)['status'], 'PASS')
        continued = new_session('Continue the existing project')
        inherit_contract(continued, contract)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            save_session(path, continued)
            continued = load_session(path)
        for qid, expected in (
            ('G06', ('agent_proposed', 'proposed', False)),
            ('I17', ('project_preset', 'defaulted', False)),
            ('G03', ('inherited_project', 'confirmed', True)),
        ):
            entry = continued['entries'][qid]
            self.assertEqual(tuple(entry[key] for key in
                                   ('source_type', 'decision_status', 'locked')), expected)
        self.assertEqual(gate(export_ledger(continued), 'prompt')['status'], 'GRILL_PASS')
        recompiled = compile_contract(continued)
        self.assertEqual(gate(recompiled, 'prompt')['status'], 'GRILL_PASS')
        self.assertEqual(next(item for item in ledger_from_contract(recompiled)['entries']
                              if item['id'] == 'G06')['basis'], 'agent_proposal')
        second = new_session('Continue again')
        inherit_contract(second, recompiled)
        self.assertEqual(second['entries']['G06']['source_type'], 'agent_proposed')
        self.assertFalse(second['entries']['G06']['locked'])

    def mixed_contract(self):
        contract = compile_contract(papercut_session())
        decision = next(item for item in contract['decisions']
                        if item['field_path'] == 'creative_intent.visual_register')
        decision.update(source_type='agent_proposed', decision_status='proposed',
                        locked=False, source_ref='agent_G06')
        self.assertEqual(validate_contract(contract)['status'], 'PASS')
        return contract

    def test_mixed_group_cannot_be_inherited_or_partially_mutate_session(self):
        session = new_session('Continue the existing project')
        before = copy.deepcopy(session)
        with self.assertRaisesRegex(GrillSessionError, 'GRILL_CONTRACT_PROVENANCE.*G06'):
            inherit_contract(session, self.mixed_contract())
        self.assertEqual(session, before)

    def test_mixed_group_blocks_projection_gate_and_compiler_entry(self):
        contract = self.mixed_contract()
        projected = ledger_from_contract(contract)
        for payload in (contract, projected):
            result = gate(payload, 'prompt')
            self.assertEqual(result['status'], 'GRILL_INVALID')
            self.assertTrue(any('GRILL_CONTRACT_PROVENANCE' in error and 'G06' in error
                                for error in result['errors']), result)
        root = Path(__file__).resolve().parents[1]
        task = json.loads((root / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        self.assertEqual(grill_gate_for(task, contract)['status'], 'GRILL_INVALID')
        self.assertEqual(_grill_gate({'task_type': 'prompt_only', 'duration_sec': 5,
                                     'aspect_ratio': '9:16',
                                     'sound': {'mode': 'ambience_only'}}, contract)['status'],
                         'GRILL_INVALID')

    def test_confirmed_user_fields_may_have_different_user_sources(self):
        contract = compile_contract(papercut_session())
        style = next(item for item in contract['decisions']
                     if item['field_path'] == 'creative_intent.visual_style')
        register = next(item for item in contract['decisions']
                        if item['field_path'] == 'creative_intent.visual_register')
        style.update(source_type='user_original', decision_status='confirmed', locked=True)
        register.update(source_type='grillme_answer', decision_status='confirmed', locked=True)
        self.assertEqual(gate(contract, 'prompt')['status'], 'GRILL_PASS')
        continued = new_session('Continue both confirmed user decisions')
        inherit_contract(continued, contract)
        self.assertTrue(continued['entries']['G06']['locked'])
        self.assertEqual(continued['entries']['G06']['source_type'], 'inherited_project')

    def test_malformed_provenance_is_invalid_without_a_traceback(self):
        for field, value in (('locked', {}), ('locked', 1),
                             ('source_type', []), ('decision_status', {})):
            contract = compile_contract(papercut_session())
            contract['decisions'][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(gate(contract, 'prompt')['status'], 'GRILL_INVALID')


if __name__ == '__main__':
    unittest.main()
