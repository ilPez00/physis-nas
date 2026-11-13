import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import document_inventory as di

PHYSIS = Path('/home/gio/.local/lib/physis/bin/physis')

class DocumentInventoryTests(unittest.TestCase):
    def test_allowlist_exclusions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); root = base/'root'; root.mkdir()
            (root/'good.txt').write_text('invoice quasarunique')
            (root/'report.pdf').write_bytes(b'%PDF-1.4')
            (root/'evil.txt.exe').write_text('bad')
            (root/'shell.txt').write_text('#!/bin/sh\n')
            (root/'node_modules').mkdir(); (root/'node_modules'/'leak.txt').write_text('bad')
            (root/'link.txt').symlink_to(base/'outside.txt')
            (base/'outside.txt').write_text('outside')
            out = di.scan(root, base/'state', allow_local=True)
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertEqual({Path(x['path']).name for x in manifest['documents']}, {'good.txt','report.pdf'})
            self.assertEqual(manifest['counts']['executable_or_script'], 1)
            self.assertGreaterEqual(manifest['counts']['excluded_directories'], 1)
            self.assertGreaterEqual(manifest['counts']['symlinks'], 1)
            self.assertEqual(manifest['counts']['unsupported_extraction'], 1)
            self.assertEqual((out.stat().st_mode & 0o777), 0o700)
            self.assertFalse((out/'corpus'/'report.pdf').exists())

    def test_partial_scan_never_deletes_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'root'; root.mkdir(); (root/'a.txt').write_text('alpha'); (root/'b.txt').write_text('beta')
            state=Path(d)/'state'; first=di.scan(root,state,allow_local=True)
            second=di.scan(root,state,allow_local=True,max_entries=1)
            self.assertTrue((first/'manifest.json').exists())
            self.assertFalse(json.loads((second/'manifest.json').read_text())['complete'])

    def test_rejects_missing_mount_symlink_root_and_state_inside(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); root=base/'root'; root.mkdir(); link=base/'link'; link.symlink_to(root)
            with self.assertRaises((ValueError,OSError)): di.scan(link,base/'state',allow_local=True)
            with self.assertRaises((ValueError,OSError)): di.scan(root,root/'state',allow_local=True)
            with self.assertRaises((ValueError,OSError)): di.scan(root,base/'state',mount=base/'missing')
            with self.assertRaises((ValueError,OSError)): di.scan(root,base/'state')

    @unittest.skipUnless(PHYSIS.is_file(), 'local Physis unavailable')
    def test_real_physis_search_maps_exact_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'root'; root.mkdir(); source=root/'invoice.txt'; source.write_text('quasarunique invoice lexical evidence\n')
            out=di.scan(root,Path(d)/'state',allow_local=True,bridge=True,physis=str(PHYSIS))
            result=di.search(out,'quasarunique',physis=str(PHYSIS))
            self.assertTrue(any(x['path']==str(source) for x in result['hits']), result)

if __name__ == '__main__': unittest.main()
