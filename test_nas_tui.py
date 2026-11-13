"""Unit tests for nas_tui pure helpers (no TUI launched)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import nas_tui


class FakeRunner:
    """Programmable stand-in for run_json."""
    def __init__(self, script):
        self.script = list(script)  # list of (ok, data) consumed in order
        self.calls = []

    def __call__(self, physis, env, args, timeout=60):
        self.calls.append(args)
        return self.script.pop(0)


class DigPlanTests(unittest.TestCase):
    def test_no_selection_is_reported_as_no_selection(self):
        kind, payload = nas_tui.dig_plan(None, '/repo')
        self.assertEqual((kind, payload), ('no-selection', None))

    def test_no_repository_is_reported_as_no_repository(self):
        kind, payload = nas_tui.dig_plan('file:invoice.txt', '')
        self.assertEqual((kind, payload), ('no-repo', None))

    def test_ready_selection_strips_the_file_prefix(self):
        kind, payload = nas_tui.dig_plan('file:invoice.txt', '/repo')
        self.assertEqual(kind, 'run')
        self.assertEqual(payload, ('invoice.txt', '/repo'))


class ScanRenderTests(unittest.TestCase):
    def test_algo_mode_labels_both_engines_and_reports_empty(self):
        data = [(['query', 'test'], {'results': ['file:a.txt']}), (['search', 'test'], {'results': []})]
        lines = nas_tui.render_scan('algo', 'test', data)
        text = '\n'.join(lines)
        self.assertIn('ALGO', text)
        self.assertIn('structural query', text)
        self.assertIn('BM25', text)
        self.assertIn('no hits', text)
        # fully empty scan: the honest empty-result language must appear
        empty = nas_tui.render_scan('algo', 'x', [(['query', 'x'], {'results': []})])
        self.assertTrue(any('empty result is a finding' in ln for ln in empty))

    def test_semantic_mode_shows_receipts_and_freshness(self):
        data = [(['explore', 'q'], {'world_revision': 'abc', 'fresh': 2, 'stale': 1,
                             'truncated': 0, 'orientation': ['o1'],
                             'sources': ['s1'], 'receipts': ['r1'], 'receipts_total': 1})]
        text = '\n'.join(nas_tui.render_scan('semantic', 'q', data))
        self.assertIn('SEMANTIC', text)
        self.assertIn('world_revision: abc', text)
        self.assertIn('receipts (1)', text)
        self.assertIn('r1', text)


class AskWorldTests(unittest.TestCase):
    def test_chat_answer_preferred(self):
        fake = FakeRunner([(True, {'text': 'real answer', 'evidence': ['e1']})])
        orig = nas_tui.run_json
        nas_tui.run_json = fake
        try:
            engine, data = nas_tui.ask_world('p', {}, 'q')
        finally:
            nas_tui.run_json = orig
        self.assertEqual(engine, 'chat')
        self.assertEqual(data['text'], 'real answer')

    def test_refusal_falls_back_to_ask_and_unknown_preserved(self):
        fake = FakeRunner([(True, {'kind': 'refusal', 'text': 'I can answer...'}),
                           (True, {'answer': 'UNKNOWN', 'confidence': 0.0,
                                   'confidence_source': 'none:no-decision', 'card': {}})])
        orig = nas_tui.run_json
        nas_tui.run_json = fake
        try:
            engine, data = nas_tui.ask_world('p', {}, 'q')
        finally:
            nas_tui.run_json = orig
        self.assertEqual(engine, 'ask')
        self.assertEqual(data['answer'], 'UNKNOWN')
        lines = nas_tui.render_answer(engine, data)
        self.assertTrue(any('nothing was invented' in ln for ln in lines))

    def test_both_engines_failing_reports_error(self):
        fake = FakeRunner([(False, {'error': 'x'}), (False, {'error': 'y'})])
        orig = nas_tui.run_json
        nas_tui.run_json = fake
        try:
            engine, data = nas_tui.ask_world('p', {}, 'q')
        finally:
            nas_tui.run_json = orig
        self.assertEqual(engine, 'error')
        self.assertIn('error', data)


if __name__ == '__main__':
    unittest.main()
