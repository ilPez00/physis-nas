import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('nas.py')
PHYSIS = Path(os.environ.get('PHYSIS_BIN') or shutil.which('physis') or 'physis')


def make_runner(root, state):
    def run(*args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--physis', str(PHYSIS), '--state', str(state), *map(str, args)],
            text=True, capture_output=True)
    return run


@unittest.skipUnless(PHYSIS.is_file(), 'local Physis binary unavailable')
class Integration(unittest.TestCase):
    def test_observe_and_search_and_refuse_missing_share(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'invoice.txt').write_text('Invoice alpha project\n')
            state = Path(d) / 'state'
            run = make_runner(root, state)
            scan = run('scan', root, '--allow-local')
            self.assertEqual(scan.returncode, 0, scan.stderr)
            self.assertFalse(json.loads(scan.stdout)['truncated'])
            query = run('search', root, 'invoice', '--allow-local')
            self.assertEqual(query.returncode, 0, query.stderr)
            self.assertTrue(any('invoice.txt' in x for x in json.loads(query.stdout)['results']))
            missing = run('scan', root / 'missing', '--allow-local')
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse((root / '.physis-next').exists())

    def test_changes_reports_delta_and_updates_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'a.txt').write_text('alpha\n')
            state = Path(d) / 'state'
            run = make_runner(root, state)
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            empty = run('changes', root, '--allow-local')
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertEqual(json.loads(empty.stdout)['changes'], [])
            (root / 'b.txt').write_text('beta\n')
            delta = run('changes', root, '--rescan', '--allow-local')
            self.assertEqual(delta.returncode, 0, delta.stderr)
            subjects = ' '.join(c.get('subject', '') for c in json.loads(delta.stdout)['changes'])
            self.assertIn('b.txt', subjects)

    def test_seal_and_verify_roundtrip_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'doc.txt').write_text('evidence\n')
            state = Path(d) / 'state'
            run = make_runner(root, state)
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            seal = run('seal', root, '--allow-local')
            self.assertEqual(seal.returncode, 0, seal.stderr)
            self.assertIn('sha256', seal.stdout)
            ok = run('verify', root, '--allow-local')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn('VERIFIED', ok.stdout)
            # Tamper with the newest packet and expect verification to fail.
            packet_dir = sorted((state).glob('*/packets/*'))[-1]
            obs = packet_dir / 'observations.jsonl'
            obs.write_text(obs.read_text() + '{"seq": 99999}\n')
            bad = run('verify', root, '--allow-local')
            self.assertNotEqual(bad.returncode, 0)

    def test_duplicates_groups_same_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'one.txt').write_text('same bytes\n')
            (root / 'two.txt').write_text('same bytes\n')
            (root / 'three.txt').write_text('different\n')
            run = make_runner(root, Path(d) / 'state')
            out = run('duplicates', root, '--allow-local')
            self.assertEqual(out.returncode, 0, out.stderr)
            data = json.loads(out.stdout)
            self.assertEqual(data['duplicate_groups'], 1)
            group = next(iter(data['groups'].values()))
            self.assertCountEqual(group, ['one.txt', 'two.txt'])

    def test_duplicates_reports_skipped_over_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            big = root / 'big.bin'
            big.write_bytes(b'x' * 16)
            run = make_runner(root, Path(d) / 'state')
            out = run('duplicates', root, '--allow-local', '--size-cap', '8')
            self.assertEqual(out.returncode, 0, out.stderr)
            data = json.loads(out.stdout)
            self.assertTrue(any('big.bin' in s for s, _ in data['skipped']))

    def test_casefile_writes_report_with_limitations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'a.txt').write_text('alpha\n')
            state = Path(d) / 'state'
            run = make_runner(root, state)
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            out = run('casefile', root, '--allow-local')
            self.assertEqual(out.returncode, 0, out.stderr)
            report = (state / 'casefile.md').read_text()
            self.assertIn('# Casefile (inventory level)', report)
            self.assertIn('## Limitations', report)
            self.assertIn('not what documents say', report)

    def test_ask_prints_refusal_as_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'a.txt').write_text('alpha\n')
            run = make_runner(root, Path(d) / 'state')
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            out = run('ask', root, 'what files exist', '--allow-local')
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn('refusal', out.stdout.lower())

    def test_dig_recovers_deleted_file_from_fixture_repository(self):
        import gzip, hashlib
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            body = b'Invoice alpha project\n'
            (root / 'invoice.txt').write_bytes(body)
            state = Path(d) / 'state'
            run = make_runner(root, state)
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            (root / 'invoice.txt').unlink()
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)

            # A one-snapshot backup repository in the physis-data-backup
            # layout: gzip manifest + sha256-addressed chunks.
            repo = Path(d) / 'backups' / 'repository'
            (repo / 'snapshots').mkdir(parents=True)
            (repo / 'chunks').mkdir()
            sha = hashlib.sha256(body).hexdigest()
            (repo / 'chunks' / sha).write_bytes(body)
            manifest = {'format': 1, 'files': {'invoice.txt': {
                'chunks': [sha], 'size': len(body), 'sha256': sha, 'mode': 0o600}}}
            (repo / 'snapshots' / '20260101T000000000000Z.json.gz').write_bytes(
                gzip.compress(json.dumps(manifest).encode()))

            dug = run('dig', root, 'invoice.txt', '--allow-local',
                      '--repository', repo)
            self.assertEqual(dug.returncode, 0, dug.stderr)
            self.assertIn('recovered', dug.stdout)
            self.assertIn('20260101T000000000000Z', dug.stdout)
            recovered = state / 'recovered' / 'invoice.txt'
            self.assertEqual(recovered.read_bytes(), body, 'exact bytes')
            self.assertFalse((root / 'invoice.txt').exists(),
                             'dig never writes into the share')

    def test_dig_reports_absence_as_a_finding(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'a.txt').write_text('alpha\n')
            state = Path(d) / 'state'
            run = make_runner(root, state)
            self.assertEqual(run('scan', root, '--allow-local').returncode, 0)
            repo = Path(d) / 'backups' / 'repository'
            (repo / 'snapshots').mkdir(parents=True)
            (repo / 'chunks').mkdir()
            dug = run('dig', root, 'never/existed.txt', '--allow-local',
                      '--repository', repo)
            self.assertNotEqual(dug.returncode, 0, 'absence must exit nonzero')
            self.assertIn('not in any retained snapshot', dug.stderr)

    def test_state_stays_outside_share(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'share'; root.mkdir()
            (root / 'a.txt').write_text('alpha\n')
            run = make_runner(root, root / 'state')
            refused = run('scan', root, '--allow-local')
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('outside', refused.stderr)


if __name__ == '__main__':
    unittest.main()
