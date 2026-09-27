"""纯mock检查预算、停机、排除项及批准守卫，不导入环境或调用SSH。"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import recovery
import launch
import runtime_guard

HERE = Path(__file__).resolve().parent


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.manifest = recovery.read(HERE / 'manifest.json')
        self.temporary = tempfile.TemporaryDirectory(dir=HERE, prefix='mock-')
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / 'run'
        self.batches = []

    def run_fake(self, decide):
        def runner(rows, index, out):
            self.batches.append(copy.deepcopy(rows))
            return [{**row, 'ok': decide(row, index) == 'success',
                     'role': 'selected' if row['episode'] in (0, 3, 6) else 'backfill',
                     'error_type': None if decide(row, index) == 'success' else decide(row, index)} for row in rows]
        with contextlib.redirect_stdout(io.StringIO()):
            code = recovery.recover(self.manifest, self.out, runner)
        return code, recovery.read(self.out / 'summary.json')

    def test_success_first_then_eight_parallel_no_duplicate(self):
        code, summary = self.run_fake(lambda *_: 'success')
        self.assertEqual(code, 0)
        self.assertEqual([(r['task'], r['episode']) for r in self.batches[0]], [('StopCube', 3)])
        self.assertEqual(len(self.batches[1]), 8)
        allrows = [r for batch in self.batches for r in batch]
        keys = {(r['task'], r['episode']) for r in allrows}
        self.assertEqual(len(keys), len(allrows))
        self.assertEqual(summary['attempted'], 22)
        self.assertTrue(all(v == 3 for v in summary['success_with_original'].values()))
        self.assertFalse(keys & {(r['task'], r['episode']) for r in self.manifest['excluded']})
        recorded = [json.loads(line) for line in (self.out / 'results.jsonl').read_text().splitlines()]
        reasons = {(r['task'], r['episode']): r['category'] for r in self.manifest['eligible']}
        for row in recorded:
            self.assertEqual(row['role'], 'selected' if row['episode'] in (0, 3, 6) else 'backfill')
            self.assertEqual(row['execution_role'], 'infra_recovery')
            self.assertEqual(row['recovery_reason'], reasons[(row['task'], row['episode'])])
        for batch in self.batches[1:]:
            self.assertEqual(len(batch), len({r['task'] for r in batch}))
        with self.assertRaises(FileExistsError):
            recovery.recover(self.manifest, self.out, lambda *_: self.fail('不得重复执行'))

    def test_true_task_failure_exhausts_at_76(self):
        code, summary = self.run_fake(lambda row, index: 'success' if index == 0 else 'DatasetGenerationError')
        self.assertEqual(code, 0)
        self.assertEqual(summary['attempted'], 76)
        self.assertEqual(summary['per_task_attempts'], {t: v['recovery_limit'] for t, v in self.manifest['limits'].items()})
        self.assertNotIn(('InsertPeg', 0), {(r['task'], r['episode']) for b in self.batches for r in b})
        self.assertNotIn(('InsertPeg', 3), {(r['task'], r['episode']) for b in self.batches for r in b})

    def test_batch_role_comes_from_frozen_selected_flag(self):
        rows = [{'task': 'StopCube', 'episode': 0}, {'task': 'StopCube', 'episode': 1}]
        specs = {('StopCube', 0): {**rows[0], 'selected': False},
                 ('StopCube', 1): {**rows[1], 'selected': True}}
        original = copy.deepcopy(specs)
        batch = recovery.batch_specs(rows, specs)
        self.assertEqual([row['_role'] for row in batch], ['backfill', 'selected'])
        self.assertEqual(specs, original)

    def test_infrastructure_error_stops_after_inflight_round(self):
        code, summary = self.run_fake(lambda row, index: 'RuntimeError' if index == 1 and row['task'] == 'StopCube' else 'success')
        self.assertEqual(code, 1)
        self.assertEqual(len(self.batches), 2)
        self.assertEqual(summary['attempted'], 9)
        self.assertEqual(len((self.out / 'results.jsonl').read_text().splitlines()), 9)

    def test_first_failure_stops_after_one(self):
        code, summary = self.run_fake(lambda *_: 'RuntimeError')
        self.assertEqual(code, 1)
        self.assertEqual(summary['attempted'], 1)
        self.assertEqual(len(self.batches), 1)

    def test_seven_task_failure_types_continue_without_retrying_identity(self):
        expected = {'SceneGenerationError', 'FailsafeTimeout', 'PlannerExhausted', 'ScrewPlanFailure',
                    'DatasetGenerationError', 'BinCollisionError', 'SpecBindingError'}
        self.assertEqual(recovery.TASK_FAILURE_TYPES, expected)
        for error_type in sorted(expected):
            with self.subTest(error_type=error_type):
                self.out = Path(self.temporary.name) / error_type
                self.batches = []
                code, summary = self.run_fake(lambda row, index: error_type if index == 1 and row['task'] == 'SwingXtimes' else 'success')
                self.assertEqual(code, 0)
                self.assertEqual(summary['attempted'], 23)
                self.assertTrue(all(v == 3 for v in summary['success_with_original'].values()))
                keys = [(r['task'], r['episode']) for batch in self.batches for r in batch]
                self.assertEqual(len(keys), len(set(keys)))
                recorded = [json.loads(line) for line in (self.out / 'results.jsonl').read_text().splitlines()]
                failed = [r for r in recorded if not r['ok']]
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]['recovery_category'], 'true_task_failure')

    def test_unknown_and_runtime_errors_stop_after_current_round(self):
        for error_type in ('RuntimeError', 'TypeError', 'UnknownError', None):
            with self.subTest(error_type=error_type):
                self.out = Path(self.temporary.name) / str(error_type)
                self.batches = []
                code, summary = self.run_fake(lambda row, index: error_type if index == 1 and row['task'] == 'SwingXtimes' else 'success')
                self.assertEqual(code, 1)
                self.assertEqual(summary['attempted'], 9)
                self.assertEqual(len(self.batches), 2)

    def test_no_approval_cannot_launch_or_call_subprocess(self):
        with patch.object(launch, 'HERE', Path(self.temporary.name)), patch.object(launch.subprocess, 'run') as run, patch.object(launch.subprocess, 'check_output') as check:
            (Path(self.temporary.name) / 'manifest.json').write_bytes((HERE / 'manifest.json').read_bytes())
            with self.assertRaises(FileNotFoundError):
                launch.check()
            run.assert_not_called()
            check.assert_not_called()

    def test_approval_must_bind_manifest_and_budget(self):
        path = Path(self.temporary.name) / 'approval.json'
        data = {'approved': True, 'run_name': self.manifest['run_name'], 'max_attempts': 76,
                'manifest_sha256': hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(),
                'user_instruction': '测试夹具，不是实际执行授权'}
        path.write_text(json.dumps(data))
        self.assertEqual(recovery.approval(HERE / 'manifest.json', path)['max_attempts'], 76)
        data['max_attempts'] = 77
        path.write_text(json.dumps(data))
        with self.assertRaises(AssertionError):
            recovery.approval(HERE / 'manifest.json', path)

    def check_source_fixture(self, status='', untracked='', code_changed=False):
        root = Path(self.temporary.name)
        here = root / 'recovery'
        here.mkdir(exist_ok=True)
        (root / 'launch-commit.txt').write_text('a' * 40)
        for name in launch.ALLOWED_DOCUMENTS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('本轮授权的文档修改\n')
        def fake_output(command, **kwargs):
            if command[1] == 'rev-parse':
                return 'a' * 40 + '\n'
            if command[1] == 'status':
                return status
            if command[1] == 'ls-files':
                return untracked
            self.fail(command)
        def fake_run(command, **kwargs):
            self.assertNotIn('a' * 40, command, '必须比较工作树而非只比较两个提交')
            self.assertIn(':(exclude)scripts/README.md', command)
            if code_changed:
                raise subprocess.CalledProcessError(1, command)
        with patch.object(launch, 'HERE', here), patch.object(launch, 'REPO', root), \
             patch.object(launch.subprocess, 'check_output', side_effect=fake_output), \
             patch.object(launch.subprocess, 'run', side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()):
            return launch.verify_source()

    def test_allowed_three_document_modifications_are_fingerprinted(self):
        status = ' M AGENTS.md\n M NEWTASK_RELEASE_V6_PLAN.md\n M scripts/README.md\n'
        result = self.check_source_fixture(status=status)
        self.assertEqual(set(result['documents']), launch.ALLOWED_DOCUMENTS)
        self.assertEqual(len(result['working_tree_status']), 3)
        self.assertTrue(all(len(v['sha256']) == 64 for v in result['documents'].values()))

    def test_other_paths_or_nonordinary_document_status_are_rejected(self):
        for status in (' M readme.md\n', ' M scripts/parity/v4_rollout.py\n', '?? scripts/extra.py\n',
                       ' D AGENTS.md\n', '?? AGENTS.md\n', 'R  old -> AGENTS.md\n'):
            with self.subTest(status=status), self.assertRaises(AssertionError):
                self.check_source_fixture(status=status)

    def test_runtime_worktree_diff_is_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.check_source_fixture(code_changed=True)

    def test_untracked_runtime_source_is_rejected_even_if_status_omits_it(self):
        with self.assertRaises(AssertionError):
            self.check_source_fixture(untracked='src/robomme/extra.py\n')

    def runtime_fixture(self):
        root = Path(self.temporary.name) / 'runtime'
        for name in ('src', 'scripts', 'tests'):
            (root / name).mkdir(parents=True, exist_ok=True)
        target = root / 'src/entry.py'
        target.write_text('VALUE = 1\n')
        document = {'schema': 'v6-runtime-tree/1', 'source_commit': runtime_guard.BASELINE,
                    'scan_roots': ['src', 'scripts', 'tests'], 'extra_suffixes': ['.py', '.json'],
                    'excluded_components': ['__pycache__'],
                    'files': {'src/entry.py': {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                             'bytes': target.stat().st_size}}}
        path = root / 'runtime-manifest.json'
        path.write_text(json.dumps(document))
        return root, path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_remote_runtime_tamper_same_length_rejected(self):
        root, manifest, digest = self.runtime_fixture()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runtime_guard.verify_tree(root, manifest, digest), 1)
        (root / 'src/entry.py').write_text('VALUE = 2\n')
        with self.assertRaisesRegex(AssertionError, '源码SHA不符'):
            runtime_guard.verify_tree(root, manifest, digest)

    def test_remote_extra_python_and_json_rejected(self):
        for suffix in ('.py', '.json'):
            with self.subTest(suffix=suffix):
                root, manifest, digest = self.runtime_fixture()
                extra = root / ('scripts/unregistered' + suffix)
                extra.write_text('{}')
                with self.assertRaisesRegex(AssertionError, '未登记'):
                    runtime_guard.verify_tree(root, manifest, digest)
                extra.unlink()

    def test_remote_runtime_manifest_tamper_rejected(self):
        root, manifest, digest = self.runtime_fixture()
        manifest.write_text(manifest.read_text() + ' ')
        with self.assertRaisesRegex(AssertionError, '清单SHA不符'):
            runtime_guard.verify_tree(root, manifest, digest)

    def test_remote_import_must_resolve_to_execution_clone(self):
        import types
        root = Path(self.temporary.name)
        module = types.SimpleNamespace(__file__='/wrong/robomme/__init__.py', __path__=['/wrong/robomme'])
        with patch.object(runtime_guard.importlib, 'import_module', return_value=module):
            with self.assertRaisesRegex(AssertionError, '导入位置不符'):
                runtime_guard.check_import(root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
