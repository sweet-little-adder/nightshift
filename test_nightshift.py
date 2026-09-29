import unittest
from unittest.mock import patch
from nightshift import (TransientToolError, call_tool, offline_plan, read_data,
                        run, validate_plan, with_retry)
from pathlib import Path

DATA = read_data(Path(__file__).parent / 'sample_incidents.json')


class AgentTests(unittest.TestCase):
    def test_workflow(self):
        out = run('api-503', DATA)
        self.assertEqual(out.severity, 'high')
        self.assertEqual(out.evidence, ['signal:api-503', 'runbook:checkout-errors'])
        self.assertEqual([t.tool for t in out.trace],
                         ['read_signal', 'find_runbook', 'read_runbook'])
        self.assertEqual(out.confidence, 'medium')

    def test_second_signal(self):
        out = run('queue-lag', DATA)
        self.assertIn('runbook:worker-backlog', out.evidence)

    def test_no_book(self):
        data = {'signals': {'x': {'service': 'new', 'severity': 'low'}}, 'runbooks': {}}
        out = run('x', data)
        self.assertEqual(out.confidence, 'low')
        self.assertEqual(out.evidence, ['signal:x'])

    def test_unknown_signal(self):
        with self.assertRaises(KeyError): run('x', DATA)

    def test_tool_allowlist(self):
        with self.assertRaises(ValueError): call_tool('delete_incident', {'id': 'api-503'}, DATA)
        with self.assertRaises(ValueError): call_tool('read_signal', {'id': 'api-503', 'extra': 1}, DATA)

    def test_plan_order(self):
        with self.assertRaises(ValueError): validate_plan([('find_runbook', {'id': 'api-503'})], 'api-503')

    def test_malformed_plan(self):
        with self.assertRaises(ValueError): validate_plan([('read_signal', {'bad': 'x'}), ('find_runbook', {'id': 'x'})], 'x')

    def test_plan_duplicate(self):
        with self.assertRaises(ValueError): validate_plan([
            ('read_signal', {'id': 'api-503'}), ('find_runbook', {'id': 'api-503'}),
            ('read_runbook', {'id': 'checkout-errors'}),
            ('read_runbook', {'id': 'checkout-errors'})], 'api-503')

    def test_budget(self):
        with self.assertRaises(ValueError): run('api-503', DATA, max_steps=2)

    def test_planner_cannot_read_other_runbook(self):
        plan = [('read_signal', {'id': 'api-503'}),
                ('find_runbook', {'id': 'api-503'}),
                ('read_runbook', {'id': 'worker-backlog'})]
        with patch('nightshift.openai_plan', return_value=plan):
            with self.assertRaises(ValueError): run('api-503', DATA, 'openai', 'key')

    def test_retry_transient(self):
        calls = 0
        original = call_tool
        def flaky(name, args, data):
            nonlocal calls
            calls += 1
            if calls < 3: raise TransientToolError('temporary')
            return original(name, args, data)
        with patch('nightshift.call_tool', side_effect=flaky):
            result, attempts = with_retry('read_signal', {'id': 'api-503'}, DATA,
                                          sleep=lambda _: None)
        self.assertEqual(attempts, 3)
        self.assertEqual(result['source'], 'signal:api-503')

    def test_retry_exhausted_returns_failure_trace(self):
        with patch('nightshift.call_tool', side_effect=TransientToolError('temporary')):
            with patch('nightshift.time.sleep', return_value=None):
                out = run('api-503', DATA)
        self.assertEqual(out.severity, 'unknown')
        self.assertEqual(out.trace[0].attempts, 3)
        self.assertEqual(out.trace[0].status, 'error')

    def test_openai_requires_key(self):
        with self.assertRaises(ValueError): run('api-503', DATA, 'openai')

    def test_invalid_severity_is_unknown(self):
        data = {'signals': {'x': {'service': 'new', 'severity': 'immediate trade'}}, 'runbooks': {}}
        self.assertEqual(run('x', data).severity, 'unknown')

    def test_structured_output(self):
        out = run('api-503', DATA).to_dict()
        self.assertEqual(set(out), {'summary', 'severity', 'evidence', 'next_steps',
                                    'confidence', 'mode', 'trace'})
        self.assertIsInstance(out['trace'], list)
