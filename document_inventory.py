"""Read-only document inventory for one explicitly authorized root.

Classifies files by extension allowlist, refuses to copy raw binaries into the
snapshot, keeps state outside the scanned root, never follows symlinks, and
never treats a partial scan as complete. Each scan writes a NEW snapshot
directory; a failed or capped scan never touches previous snapshots.

Security posture:
- the root may not itself be a symlink, even with allow_local;
- state must live outside the scanned root;
- without allow_local, the root (or the declared `mount=`) must be an actual
  mount point;
- corpus/ holds extracted text only — binaries are recorded in the manifest
  with extraction='unsupported' and never copied;
- scripts and executables (shebang or executable extension) are counted and
  excluded from the document set.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                        '.physis-next', '.physis', '$RECYCLE.BIN', 'System Volume Information'}
TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.log', '.eml', '.rst'}
DOC_EXTENSIONS = {'.pdf', '.docx', '.odt', '.rtf', '.xlsx', '.pptx'}
EXECUTABLE_EXTENSIONS = {'.exe', '.sh', '.bat', '.cmd', '.bin', '.so', '.dll', '.pyd'}  # documented; blocked via the allowlist-first rule above
READ_CAP = 1024 * 1024


def _reject(root, state, allow_local, mount):
    if root.is_symlink():
        raise ValueError('root may not be a symlink; use the real mount point')
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be a directory')
    declared = root
    if mount is not None:
        declared = Path(mount).resolve(strict=True)
    if not allow_local and not os.path.ismount(declared):
        raise ValueError('root must be an existing mount point (or use allow_local for fixtures)')
    state = state.expanduser().resolve()
    if state == root or root in state.parents or state in root.parents:
        raise ValueError('state must be outside the scanned root')
    return root, state


def _classify(rel, path):
    """Return (kind, extraction) for one regular file.

    The extension allowlist decides first: a non-allowlisted extension is
    blocked (this includes executables such as .exe and disguised
    double-extension files like evil.txt.exe). Shebang content reclassifies an
    allowlisted text file as a script.
    """
    ext = path.suffix.lower()
    if ext not in TEXT_EXTENSIONS and ext not in DOC_EXTENSIONS:
        return 'blocked_extension', None
    try:
        with path.open('rb') as fh:
            head = fh.read(2)
    except OSError:
        return 'unreadable', None
    if head == b'#!':
        return 'executable_or_script', None
    if ext in TEXT_EXTENSIONS:
        return 'document', 'text'
    return 'document', 'unsupported'


def scan(root, state, allow_local=False, mount=None, max_entries=None,
         bridge=False, physis='physis', exclude_dirs=()):
    root, state = _reject(Path(root), Path(state), allow_local, mount)
    digest = hashlib.sha256(os.fsencode(root)).hexdigest()[:24]
    base = state / digest
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    snapshot = base / f'{time.strftime("%Y%m%dT%H%M%S")}-{len(list(base.iterdir())) + 1:04d}'
    snapshot.mkdir(mode=0o700)
    corpus = snapshot / 'corpus'
    corpus.mkdir(mode=0o700)

    documents, counts = [], {'executable_or_script': 0, 'excluded_directories': 0,
                             'symlinks': 0, 'unsupported_extraction': 0,
                             'blocked_extensions': 0, 'unreadable': 0, 'files_seen': 0}
    complete = True
    seen = 0
    skip = DEFAULT_EXCLUDE_DIRS | set(exclude_dirs)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        excluded = [d for d in dirnames if d in skip or (Path(dirpath) / d).is_symlink()]
        counts['excluded_directories'] += len([d for d in excluded if (Path(dirpath) / d).exists()])
        dirnames[:] = [d for d in dirnames if d not in skip and not (Path(dirpath) / d).is_symlink()]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                counts['symlinks'] += 1
                continue
            seen += 1
            if max_entries is not None and seen > max_entries:
                complete = False
                break
            rel = path.relative_to(root)
            try:
                kind, extraction = _classify(rel, path)
            except OSError:
                kind, extraction = 'unreadable', None
            counts['files_seen'] += 1
            if kind == 'document':
                documents.append({'path': str(path), 'rel': str(rel), 'size': path.stat().st_size,
                                  'extraction': extraction})
                if extraction == 'text':
                    try:
                        text = path.read_text(errors='replace')[:READ_CAP]
                        (corpus / str(rel).replace('/', '__')).write_text(text)
                    except OSError:
                        counts['unreadable'] += 1
                else:
                    counts['unsupported_extraction'] += 1
            elif kind == 'executable_or_script':
                counts['executable_or_script'] += 1
            elif kind == 'blocked_extension':
                counts['blocked_extensions'] += 1
            else:
                counts['unreadable'] += 1
        if not complete:
            break

    manifest = {'root': str(root), 'complete': complete, 'entries_seen': seen,
                'documents': documents, 'counts': counts,
                'note': 'reported inventory, not certified truth; a partial scan is marked incomplete, never silently truncated'}
    (snapshot / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    if bridge:
        store = snapshot / 'store'
        store.mkdir(mode=0o700)
        env = os.environ.copy()
        env['PHYSIS_STORE_DIR'] = str(store)
        result = subprocess.run([physis, 'observe', str(root), '--json'],
                                env=env, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or 'physis observe failed')
    return snapshot


def search(snapshot, question, physis='physis'):
    manifest = json.loads((Path(snapshot) / 'manifest.json').read_text())
    root = Path(manifest['root'])
    store = Path(snapshot) / 'store'
    if not store.is_dir():
        raise ValueError('snapshot has no observation store; scan with bridge=True first')
    env = os.environ.copy()
    env['PHYSIS_STORE_DIR'] = str(store)
    result = subprocess.run([physis, 'query', question, '--path', str(root), '--json'],
                            env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or 'physis query failed')
    data = json.loads(result.stdout)
    hits, seen = [], set()
    for raw in data.get('results', []):
        token = raw if isinstance(raw, str) else json.dumps(raw)
        for part in token.split(','):
            part = part.strip()
            for prefix in ('file:', 'document:'):
                if part.startswith(prefix):
                    rel = part[len(prefix):].split('::')[0]
                    path = (root / rel).resolve()
                    if str(path) not in seen and path.is_file() and root in path.parents:
                        seen.add(str(path))
                        hits.append({'path': str(path), 'raw': token})
                    break
    return {'question': question, 'hits': hits, 'raw_results': data.get('results', []),
            'note': 'hits are mapped back to exact original paths; unmapped raw results are kept for audit'}


if __name__ == '__main__':
    print('usage: import document_inventory; see --help in nas.py', file=sys.stderr)
    raise SystemExit(2)
