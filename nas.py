#!/usr/bin/env python3
"""Read-only Physis inventory for one explicitly mounted share.

Commands:
  scan        observe the share into this share's own observation log
  search Q    structural search over the observed world
  changes     what the log recorded since the previous scan (use --rescan to observe first)
  seal        write an audit packet (append-only, hash-sealed) into the state dir
  verify      re-hash and verify the newest (or a named) audit packet
  duplicates  group files by content hash (size-capped, read-only)
  casefile    compose a markdown inventory report: scope, chronology, duplicates, limits
  ask Q       model-free question over the share's world; refusals are printed as refusals
  dig PATH    recover a deleted file's exact bytes from a backup repository
              (joins the world's tombstone to the newest snapshot manifest
              holding the file; every chunk is hash-verified). Requires
              --repository pointing at a physis-data-backup repository whose
              manifest paths are relative to this share. Recovered bytes are
              written OUTSIDE the share (default: <state>/recovered/) — the
              share stays read-only.
  serve       hand the share's world to an agent over MCP stdio (replaces this process)

Everything is read-only on the share. State lives outside the share, one store
per canonical mount path. Absent results are not proof of absence: inspect
`truncated` and `skipped_files`, and remember a scan never proves every file
was readable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_SIZE_CAP = 50 * 1024 * 1024


def run_physis(physis, env, args, check=False):
    result = subprocess.run([physis, *args], env=env, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f'physis exited {result.returncode}')
    return result


def physis_json(physis, env, args):
    result = run_physis(physis, env, args)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f'physis exited {result.returncode}')
    return json.loads(result.stdout)


def prepare(share, state_root, allow_local):
    root = share.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('share must be a directory')
    if not allow_local and not os.path.ismount(root):
        raise ValueError('share must be an existing mount point (or use --allow-local for fixtures)')
    state = state_root.expanduser().resolve()
    if state == root or root in state.parents:
        raise ValueError('state must be outside the scanned share')
    # Separate stores avoid mixing observations between independently mounted shares.
    store = state / hashlib.sha256(os.fsencode(root)).hexdigest()[:24]
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PHYSIS_STORE_DIR'] = str(store)
    return root, store, env


def newest_seq(physis, env, root):
    data = physis_json(physis, env, ['history', '--limit', '1', '--json', '--path', str(root)])
    rows = data.get('rows') or data.get('observations') or []
    return max((int(r['seq']) for r in rows if 'seq' in r), default=0)


def read_last_seq(store):
    marker = store / 'last_seq'
    try:
        return int(marker.read_text())
    except (OSError, ValueError):
        return 0


def write_last_seq(store, seq):
    (store / 'last_seq').write_text(str(seq))


def cmd_scan(physis, env, root, extra):
    if extra.max_files < 1:
        raise ValueError('--max-files must be positive')
    args = [physis, 'observe', str(root), '--max-files', str(extra.max_files), '--json']
    for pattern in extra.exclude:
        args.extend(['--exclude', pattern])
    result = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr, end='')
        return result.returncode
    out = json.loads(result.stdout)
    print(json.dumps(out, indent=2))
    write_last_seq(env['_store'], newest_seq(physis, env, root))
    return 0


def cmd_search(physis, env, root, question):
    result = run_physis(physis, env, ['query', question, '--path', str(root), '--json'])
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr, end='')
        return result.returncode
    print(json.dumps(json.loads(result.stdout), indent=2))
    return 0


def cmd_changes(physis, env, root, args):
    if args.rescan:
        scan = subprocess.run([physis, 'observe', str(root), '--json'], env=env, capture_output=True, text=True, check=False)
        if scan.returncode:
            print(scan.stderr or scan.stdout, file=sys.stderr, end='')
            return scan.returncode
    since = read_last_seq(env['_store']) + 1  # changes are "at or after"; +1 skips the already-recorded scan rows
    data = physis_json(physis, env, ['changes', '--since-seq', str(since), '--json', '--path', str(root)])
    rows = data.get('changes') or []
    if not rows:
        print(json.dumps({'since_seq': since, 'changes': [], 'note': 'no recorded changes after this seq'}, indent=2))
    else:
        print(json.dumps({'since_seq': since, 'count': len(rows), 'changes': rows}, indent=2))
    top = newest_seq(physis, env, root)
    write_last_seq(env['_store'], top)
    return 0


def newest_packet(store):
    packets = sorted((store / 'packets').glob('*')) if (store / 'packets').is_dir() else []
    return packets[-1] if packets else None


def cmd_seal(physis, env, root, store):
    packets = store / 'packets'
    packets.mkdir(mode=0o700, exist_ok=True)
    out = packets / f'packet-{len(list(packets.iterdir())) + 1:04d}'
    result = run_physis(physis, env, ['packet', '--out', str(out), '--path', str(root)])
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr, end='')
        return result.returncode
    print(result.stdout, end='')
    return 0


def cmd_verify(physis, env, root, store, packet_path):
    target = Path(packet_path) if packet_path else newest_packet(store)
    if not target or not target.is_dir():
        print('physis-nas: no audit packet found; run seal first', file=sys.stderr)
        return 1
    result = run_physis(physis, env, ['packet-verify', str(target)])
    print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result.returncode


def iter_files(root, cap, exclude):
    files, skipped = [], []
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(rel.match(pat) for pat in exclude):
            continue
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > cap:
                skipped.append((str(rel), 'over size cap'))
                continue
            files.append((rel, path))
        except OSError as exc:
            skipped.append((str(rel), str(exc)))
    return files, skipped


def content_hashes(root, cap, exclude):
    groups = {}
    files, skipped = iter_files(root, cap, exclude)
    for rel, path in files:
        h = hashlib.sha256()
        try:
            with path.open('rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
        except OSError as exc:
            skipped.append((str(rel), str(exc)))
            continue
        groups.setdefault(h.hexdigest(), []).append(str(rel))
    return groups, skipped


def cmd_duplicates(root, args):
    groups, skipped = content_hashes(root, args.size_cap, args.exclude)
    dupes = {h: paths for h, paths in groups.items() if len(paths) > 1}
    print(json.dumps({
        'duplicate_groups': len(dupes),
        'duplicate_files': sum(len(p) for p in dupes.values()),
        'groups': dupes,
        'skipped': skipped,
        'note': 'same content hash, computed locally with a size cap; unreadable and over-cap files are listed, not silently dropped',
    }, indent=2))
    return 0


def cmd_casefile(physis, env, root, store, args):
    hist = physis_json(physis, env, ['history', '--limit', str(args.limit), '--json', '--path', str(root)])
    rows = hist.get('rows') or hist.get('observations') or []
    groups, skipped = content_hashes(root, DEFAULT_SIZE_CAP, args.exclude)
    dupes = {h: p for h, p in groups.items() if len(p) > 1}
    files, _ = iter_files(root, DEFAULT_SIZE_CAP, args.exclude)
    files = sorted(str(rel) for rel, _ in files)
    lines = ['# Casefile (inventory level)', '',
             f'- Scope: {root}', f'- Files: {len(files)}', f'- Duplicate groups: {len(dupes)}',
             f'- Skipped (unreadable or over cap): {len(skipped)}', '',
             '## Chronology (observation timestamps, newest first)', '']
    for r in rows[:args.limit]:
        lines.append(f"- `{r.get('at')}` seq {r.get('seq')} {r.get('source')}/{r.get('produced_by')}: {r.get('subject')} — {r.get('body')}")
    lines += ['', '## Duplicates (same content hash)', '']
    if dupes:
        for h, paths in sorted(dupes.items()):
            lines.append(f'- {h[:16]}…: {", ".join(paths)}')
    else:
        lines.append('- none found within the size cap')
    lines += ['', '## Limitations', '',
              '- This report is file-level only: it records what the filesystem showed, not what documents say.',
              '- Chronology entries are observation times recorded by this tool, not document dates.',
              '- Skipped and unreadable files are listed in the scan output; absence here is not proof of absence.',
              '- Document-level dating, amounts and claims are the job of the on-platform Casefiles skill, not this prototype.']
    (store.parent / 'casefile.md').write_text('\n'.join(lines) + '\n')
    print(f'casefile written to {store.parent / "casefile.md"}')
    return 0


def cmd_ask(physis, env, root, question):
    result = run_physis(physis, env, ['chat', '--once', question, '--json', '--path', str(root)])
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr, end='')
        return result.returncode
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(result.stdout, end='')
        return 0
    if data.get('kind') == 'refusal':
        print('refusal (the engine only answers supported question shapes):')
    print(data.get('text', result.stdout))
    return 0


def cmd_dig(physis, env, root, state, args):
    """Recover a deleted file from a backup repository, honestly labelled.

    The recovered bytes are written outside the share; the report names the
    source snapshot and the tombstone sequence. Absence is printed as a
    finding (the snapshot span searched), never guessed around.
    """
    dest = args.out or (Path(state) / 'recovered' / Path(args.path).name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run_physis(physis, env, [
        'dig', args.path, '--root', str(root),
        '--repository', str(args.repository), '--out', str(dest), '--json',
    ])
    if result.returncode:
        # physis dig exits 2 with the typed absence (or a hash refusal) on
        # stderr. Relay it verbatim: a failed dig must look failed.
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        return result.returncode
    report = json.loads(result.stdout)
    print(f"recovered {report['path']} -> {report.get('written_to') or dest}")
    print(f"  source: {report['source_snapshot']} ({report['size']} bytes)")
    if report.get('tombstone_seq') is not None:
        print(f"  deleted in the world; last seen seq {report['tombstone_seq']}")
    else:
        print("  no tombstone recorded for this path (still live, or never scanned)")
    print("  every chunk sha256-verified against the manifest")
    return 0


def cmd_serve(physis, env, root):
    os.execvpe(physis, [physis, 'serve', '--stdio', '--path', str(root)], env)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--physis', default='physis', help='Physis CLI executable')
    p.add_argument('--state', type=Path, default=Path.home() / '.local/share/physis-nas')
    sub = p.add_subparsers(dest='command', required=True)
    for name, need_share in (('scan', True), ('search', True), ('changes', True), ('seal', True),
                             ('verify', True), ('duplicates', True), ('casefile', True),
                             ('ask', True), ('dig', True), ('serve', True)):
        cmd = sub.add_parser(name)
        if need_share:
            cmd.add_argument('share', type=Path, help='Exact mount point, not a subdirectory')
        if name == 'search':
            cmd.add_argument('question')
        if name == 'ask':
            cmd.add_argument('question')
        if name == 'verify':
            cmd.add_argument('packet', nargs='?', default=None, help='Packet dir; default: newest')
        if name == 'serve':
            cmd.add_argument('--allow-local', action='store_true')
        else:
            cmd.add_argument('--allow-local', action='store_true', help='Allow local fixture directory; NOT safe for unmounted shares')
        if name in ('scan', 'duplicates', 'casefile'):
            cmd.add_argument('--exclude', action='append', default=[])
        if name == 'scan':
            cmd.add_argument('--max-files', type=int, default=4000)
        if name == 'changes':
            cmd.add_argument('--rescan', action='store_true', help='Observe the share first, then report the delta')
        if name == 'duplicates':
            cmd.add_argument('--size-cap', type=int, default=DEFAULT_SIZE_CAP)
        if name == 'casefile':
            cmd.add_argument('--limit', type=int, default=50)
        if name == 'dig':
            cmd.add_argument('path', help='Share-relative path (or file:<rel> id) as the world knows it')
            cmd.add_argument('--repository', required=True, type=Path,
                             help='Backup repository to dig in (physis-data-backup layout)')
            cmd.add_argument('--out', type=Path, default=None,
                             help='Where to write the recovered bytes (default: <state>/recovered/<basename>)')
    a = p.parse_args()
    try:
        if a.command == 'duplicates':
            root, _, _ = prepare(a.share, a.state, a.allow_local)
            return cmd_duplicates(root, a)
        root, store, env = prepare(a.share, a.state, a.allow_local)
        env['_store'] = store  # internal handle for change tracking
        if a.command == 'scan':
            return cmd_scan(a.physis, env, root, a)
        if a.command == 'search':
            return cmd_search(a.physis, env, root, a.question)
        if a.command == 'changes':
            return cmd_changes(a.physis, env, root, a)
        if a.command == 'seal':
            return cmd_seal(a.physis, env, root, store)
        if a.command == 'verify':
            return cmd_verify(a.physis, env, root, store, a.packet)
        if a.command == 'casefile':
            return cmd_casefile(a.physis, env, root, store, a)
        if a.command == 'ask':
            return cmd_ask(a.physis, env, root, a.question)
        if a.command == 'dig':
            return cmd_dig(a.physis, env, root, a.state, a)
        if a.command == 'serve':
            return cmd_serve(a.physis, env, root)
        return 2
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f'physis-nas: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
