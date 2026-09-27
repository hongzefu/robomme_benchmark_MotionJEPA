"""复制小型元数据夹具，以替身 tmux 验证续行；绝不启动真实作业。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = REPO / 'artifacts/newtask-v6/v6-s2-20260926-01'


class ContinueTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='test-continue-', dir=HERE)
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.launch = self.root / 'artifacts/newtask-v6/s4-launch'
        self.launch.mkdir(parents=True)
        self.s2 = self.root / SOURCE.relative_to(REPO)
        self.s2.mkdir(parents=True)
        for name in ('manifest.json', 'run.log', 'report.md'):
            shutil.copyfile(SOURCE / name, self.s2 / name)
        for path in SOURCE.glob('summary-*.json'):
            shutil.copyfile(path, self.s2 / path.name)
        report = json.loads((SOURCE / 'report.json').read_text())
        for row in report['identities']:
            destination = self.s2 / 'episodes' / row['id']
            destination.mkdir(parents=True)
            for name in ('started.json', 'result.json', 'summary.jsonl'):
                shutil.copyfile(SOURCE / 'episodes' / row['id'] / name, destination / name)
            for media in row['hdf5'] + row['videos']:
                path = self.root / media['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x')
                media['bytes'] = 1
        (self.s2 / 'report.json').write_text(json.dumps(report))
        self.initial_report = (self.s2 / 'report.json').read_bytes()
        self.s3 = self.root / 'artifacts/newtask-v6/v6-s3-20260926-01'
        self.s3.mkdir()
        for name in ('smoke_manifest.json', 'remaining_manifest.json'):
            (self.s3 / name).write_text('{}')
        script = (HERE / 'continue_after_s2.sh').read_text().replace(f'ROOT={REPO}', f'ROOT={self.root}')
        (self.launch / 'continue_after_s2.sh').write_text(script)
        shutil.copyfile(HERE / 's2_gate.py', self.launch / 's2_gate.py')
        (self.launch / 'launch-commit.txt').write_text('a' * 40 + '\n')
        for name in ('uv.lock', 'pyproject.toml'):
            (self.root / name).write_text('')
        binaries = self.root / 'bin'
        binaries.mkdir()
        fake_git = '#!/bin/sh\nif [ "$1" = rev-parse ]; then echo ' + 'a' * 40 + '; fi\nexit 0\n'
        fake_uv = f'#!/bin/sh\nshift 4\nexec "{sys.executable}" "$@"\n'
        fake_tmux = f'''#!{sys.executable}
import json, pathlib, sys
root = pathlib.Path({str(self.root)!r})
state = root / 'tmux-state.json'
sessions = json.loads(state.read_text()) if state.exists() else []
args = sys.argv[1:]
if args[0] == 'has-session':
    raise SystemExit(0 if args[2].lstrip('=') in sessions else 1)
assert args[0] == 'new-session', args
name = args[args.index('-s') + 1]
assert name not in sessions
with (root / 'dispatch.jsonl').open('a') as handle:
    handle.write(json.dumps(args) + '\\n')
sessions.append(name)
state.write_text(json.dumps(sessions))
'''
        for name, body in [('git', fake_git), ('uv', fake_uv), ('tmux', fake_tmux)]:
            path = binaries / name
            path.write_text(body)
            path.chmod(0o700)
        self.env = {**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH']}

    def run_script(self, *args):
        return subprocess.run(['bash', str(self.launch / 'continue_after_s2.sh'), *args],
                              env=self.env, capture_output=True, text=True, timeout=20)

    def dispatches(self):
        path = self.root / 'dispatch.jsonl'
        return path.read_text().splitlines() if path.exists() else []

    def test_old_report_check_and_three_fake_branches_resume(self):
        checked = self.run_script('--check')
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn('missing=0', checked.stdout)
        self.assertEqual(self.dispatches(), [])
        first = self.run_script()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(len(self.dispatches()), 3)
        second = self.run_script()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(self.dispatches()), 3)
        self.assertEqual((self.s2 / 'report.json').read_bytes(), self.initial_report)

    def test_missing_result_fails_without_dispatch(self):
        next((self.s2 / 'episodes').glob('*/result.json')).unlink()
        result = self.run_script('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.dispatches(), [])

    def test_nonzero_metric_mismatch_fails(self):
        path = self.s2 / 'report.json'
        report = json.loads(path.read_text())
        report['totals']['success'] += 1
        path.write_text(json.dumps(report))
        self.assertNotEqual(self.run_script('--check').returncode, 0)
        self.assertEqual(self.dispatches(), [])

    def test_missing_nonzero_metric_fails(self):
        path = self.s2 / 'report.json'
        report = json.loads(path.read_text())
        del report['totals']['failed']
        path.write_text(json.dumps(report))
        self.assertNotEqual(self.run_script('--check').returncode, 0)

    def test_completed_branches_not_dispatched(self):
        (self.s3 / 'run.log').write_text('NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0\nEXIT_CODE=0\n')
        (self.launch / 'logs').mkdir()
        for job, count in [('61890467', 26), ('61890468', 29)]:
            (self.launch / 'logs' / f'{job}.log').write_text(f'cells={count}\nEXIT_CODE=0\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('state=COMPLETE'), 3)
        self.assertEqual(self.dispatches(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
