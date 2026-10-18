import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from src.optimization import optimize
from src.optimization.optimizer import call_model, extract_rtl, source_hash, rtl_fingerprint


class OptimizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rtl = self.root / 'source.v'
        self.source = 'module top(input a, output b); assign b=a; endmodule\n'
        self.rtl.write_text(self.source)
        self.env = patch.dict(os.environ, {
            'LLM_BACKEND': 'custom', 'LLM_BASE_URL': 'https://example.invalid/v1',
            'LLM_MODEL': 'test', 'LLM_API_KEY': 'secret-test-value',
            'LLM_TIMEOUT_SECONDS': '2'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_opt(self, feedback=None, **kw):
        return optimize(self.rtl, feedback, output_dir=self.root / 'out', env_file=None, **kw)

    def test_mock_unique_and_source_preserved(self):
        a, b = self.run_opt(backend='mock'), self.run_opt(backend='mock')
        self.assertEqual(a['status'], 'success')
        self.assertTrue(a['is_mock'])
        self.assertNotEqual(a['candidate_path'], b['candidate_path'])
        self.assertEqual(Path(a['candidate_path']).read_text(), self.source)
        self.assertEqual(self.rtl.read_text(), self.source)

    def test_feedback_prompt_and_real_marker(self):
        feedback = {'verify': {'status': 'failed', 'equivalent': False}, 'baseline': {'area': 12}}
        with patch('src.optimization.optimizer.call_model', return_value='```verilog\n'+self.source+'```') as call:
            result = self.run_opt(feedback)
        self.assertEqual(result['strategy'], 'repair_equivalence')
        self.assertFalse(result['is_mock'])
        self.assertIn(self.source, call.call_args.args[0])
        self.assertIn('"area": 12', call.call_args.args[0])

    def test_strategy_feedback(self):
        self.assertEqual(self.run_opt({'evaluate': {'status': 'success', 'timing_met': False}}, backend='mock')['strategy'], 'timing_restructure')
        self.assertEqual(self.run_opt({'tried_strategies': ['area_simplify']}, backend='mock')['strategy'], 'resource_share')
        self.assertEqual(self.run_opt({'verify': {'status': 'error', 'equivalent': False}}, backend='mock')['strategy'], 'area_simplify')

    def test_failures(self):
        cases = [('', 'empty_output', 'failed'), ('  \n', 'empty_output', 'failed'),
                 ('Explanation only', 'extraction_failed', 'failed'),
                 ('```verilog\nmodule x();\n```', 'extraction_failed', 'failed'),
                 (HTTPError('https://example.invalid', 401, 'secret-test-value', {}, None), 'api_error', 'error'),
                 (TimeoutError('secret-test-value'), 'api_timeout', 'timeout')]
        for value, kind, status in cases:
            with self.subTest(kind=kind):
                options = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
                with patch('src.optimization.optimizer.call_model', **options):
                    result = self.run_opt()
                self.assertEqual(result['error_type'], kind)
                self.assertEqual(result['status'], status)
                self.assertIsNone(result['candidate_path'])
                self.assertNotIn('secret-test-value', json.dumps(result))

    def test_input_config_save_errors(self):
        self.assertEqual(self.run_opt([])['error_type'], 'input_error')
        with patch.dict(os.environ, {'LLM_API_KEY': ''}):
            self.assertEqual(self.run_opt()['error_type'], 'config_error')
        with patch('src.optimization.optimizer.Path.mkdir', side_effect=OSError()):
            self.assertEqual(self.run_opt(backend='mock')['error_type'], 'save_error')

    def test_extraction_ambiguity_and_comments(self):
        self.assertIsNone(extract_rtl('```verilog\n// module fake endmodule\n```'))
        block = '```systemverilog\n'+self.source+'```\n'
        self.assertIsNone(extract_rtl(block+block))
        self.assertEqual(extract_rtl(block)[1], '.sv')

    def test_http_adapter_contract(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"choices":[{"message":{"content":"hello"}}]}'
        with patch('src.optimization.optimizer.request.build_opener') as factory:
            factory.return_value.open.return_value = response
            self.assertEqual(call_model('prompt', dict(os.environ), 2), 'hello')
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, 'https://example.invalid/v1/chat/completions')
            self.assertEqual(json.loads(req.data)['messages'][0]['content'], 'prompt')

    def test_history_strategy_and_context_isolation(self):
        history = self.root / 'history.jsonl'
        first = self.run_opt(backend='mock', context={'design_id': 'one'}, history_path=history)
        second = self.run_opt(backend='mock', context={'design_id': 'one'}, history_path=history)
        other = self.run_opt(backend='mock', context={'design_id': 'two'}, history_path=history)
        self.assertEqual(first['strategy'], 'area_simplify')
        self.assertEqual(second['strategy'], 'resource_share')
        self.assertEqual(other['strategy'], 'area_simplify')
        self.assertTrue(second['is_duplicate'])
        self.assertEqual(second['duplicate_of'], 'current_input')
        self.assertEqual(len(history.read_text(encoding='utf-8').splitlines()), 3)

    def test_history_marks_repeated_new_candidate(self):
        history = self.root / 'history.jsonl'
        changed = self.source.replace('assign b=a;', 'assign b=~(~a);')
        with patch('src.optimization.optimizer.call_model', return_value='```verilog\n'+changed+'```'):
            first = self.run_opt(history_path=history)
            second = self.run_opt(history_path=history)
        self.assertFalse(first['is_duplicate'])
        self.assertTrue(second['is_duplicate'])
        self.assertEqual(second['duplicate_of'], first['run_id'])

    def test_mock_history_not_used_as_real_history(self):
        history = self.root / 'history.jsonl'
        self.run_opt(backend='mock', history_path=history)
        with patch('src.optimization.optimizer.call_model', return_value='```verilog\n'+self.source+'```'):
            real = self.run_opt(history_path=history)
        self.assertEqual(real['strategy'], 'area_simplify')

    def test_feedback_marker_and_bounded_prompt(self):
        feedback = {'is_mock': True, 'verify': {'status': 'failed', 'equivalent': False,
                    'error_log': 'x' * 10000}, 'api_key': 'should-not-appear'}
        result = self.run_opt(feedback, backend='mock', context={'top': 'top'})
        prompt = Path(result['prompt_path']).read_text(encoding='utf-8')
        record = Path(result['record_path']).read_text(encoding='utf-8')
        self.assertTrue(result['feedback_is_mock'])
        self.assertIn('[truncated]', prompt)
        self.assertNotIn('should-not-appear', prompt + record)
        self.assertNotIn('secret-test-value', prompt + record)
        self.assertIn('"top": "top"', prompt)
        self.assertLess(len(prompt), 5000)

    def test_metadata_and_truncated_response(self):
        answer = {'content': '```verilog\n'+self.source+'```', 'usage': {'total_tokens': 23},
                  'model': 'test-actual', 'finish_reason': 'length'}
        with patch('src.optimization.optimizer.call_model', return_value=answer):
            result = self.run_opt()
        self.assertEqual(result['error_type'], 'output_truncated')
        self.assertEqual(result['usage']['total_tokens'], 23)
        self.assertIsNone(result['candidate_path'])
        self.assertTrue(Path(result['record_path']).is_file())

    def test_invalid_history_context_and_budgets(self):
        bad = self.root / 'bad.jsonl'
        bad.write_text('not-json', encoding='utf-8')
        self.assertEqual(self.run_opt(history_path=bad)['error_type'], 'input_error')
        bad.write_text('{"status":"success"}', encoding='utf-8')
        self.assertEqual(self.run_opt(history_path=bad)['error_type'], 'input_error')
        self.assertEqual(self.run_opt(context=[])['error_type'], 'input_error')
        self.assertEqual(self.run_opt({'tried_strategies': [None]})['error_type'], 'input_error')
        with patch.dict(os.environ, {'LLM_MAX_TOKENS': '0'}):
            with patch('src.optimization.optimizer.call_model') as call:
                self.assertEqual(self.run_opt()['error_type'], 'config_error')
                call.assert_not_called()

    def test_text_hash_not_semantic_equivalence(self):
        self.assertEqual(source_hash(self.source), source_hash(self.source.replace('\n', '\r\n')))
        self.assertNotEqual(source_hash(self.source), source_hash(self.source + '// comment\n'))

    def test_fingerprint_ignores_cosmetics_preserves_tokens(self):
        self.assertEqual(rtl_fingerprint(self.source), rtl_fingerprint('// note\n'+self.source))
        self.assertEqual(rtl_fingerprint('assign b = a;'), rtl_fingerprint('assign b=/*x*/a;'))
        self.assertNotEqual(rtl_fingerprint('a b'), rtl_fingerprint('ab'))
        self.assertNotEqual(rtl_fingerprint('a >> > b'), rtl_fingerprint('a >>> b'))
        self.assertNotEqual(rtl_fingerprint('"a b"'), rtl_fingerprint('"ab"'))

    def test_comment_only_change_is_duplicate(self):
        with patch('src.optimization.optimizer.call_model', return_value='```verilog\n// comment\n'+self.source+'```'):
            result = self.run_opt()
        self.assertTrue(result['is_duplicate'])
        self.assertEqual(result['duplicate_of'], 'current_input')

    def test_demo_uses_original_input_and_labels_feedback(self):
        from src.optimization.demo import run_demo
        for name, filename in [('popcount3', 'popcount3_v1_behavioral.v'), ('addsubz', 'addsubz_v1_behavioral.v')]:
            folder = self.root / 'demo/case/bench' / name
            folder.mkdir(parents=True)
            (folder / filename).write_text(self.source, encoding='utf-8')
        summary = run_demo(self.root / 'demo', self.root / 'sessions', backend='mock', env_file=None)
        self.assertEqual(len(summary['calls']), 3)
        self.assertEqual(summary['calls'][-1]['result']['strategy'], 'timing_restructure')
        self.assertTrue(summary['calls'][-1]['result']['feedback_is_mock'])
        records = [json.loads(Path(c['result']['record_path']).read_text(encoding='utf-8')) for c in summary['calls']]
        self.assertEqual(records[1]['source_path'], records[2]['source_path'])
        self.assertEqual(summary['verification'], 'not_run')


if __name__ == '__main__':
    unittest.main()
