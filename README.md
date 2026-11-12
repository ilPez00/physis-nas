# Physis NAS — local prototype

Read-only inventory, change tracking and evidence tooling for an explicitly
mounted share, using the existing Physis CLI. A separate local index is kept
for each canonical mount path. This is not a UGREEN Skill or a hackathon
submission, and UGREEN runtime compatibility has not been established.

The hackathon deliverable itself lives in the public repository
`ilPez00/physis-ugreen` (skill, fixtures, proposal). This repository is the
lab: the prototype CLI, the document inventory module, and the working notes
behind the submission.

## Requirements

- Python 3 and a working `physis` CLI. On this machine the existing binary is
  `/home/gio/dev/physis-next/target/debug/physis`.
- A mounted NAS share. This tool does not mount shares or manage credentials.

## Commands

```sh
P=/home/gio/dev/physis-next/target/debug/physis
python3 nas.py --physis $P scan    /path/to/mount --max-files 4000 --exclude '*.secret'
python3 nas.py --physis $P search  /path/to/mount invoice
python3 nas.py --physis $P changes /path/to/mount --rescan   # delta since previous scan
python3 nas.py --physis $P seal    /path/to/mount            # hash-sealed audit packet
python3 nas.py --physis $P verify  /path/to/mount            # re-hash and verify it
python3 nas.py --physis $P duplicates /path/to/mount         # same-content groups, size-capped
python3 nas.py --physis $P casefile /path/to/mount            # markdown inventory report
python3 nas.py --physis $P ask     /path/to/mount "state of file:invoice.txt"
python3 nas.py --physis $P serve   /path/to/mount            # MCP stdio over this share's world
```

- `changes` reports what the log recorded since the previous scan; use
  `--rescan` to observe first. The delta marker is per-share state.
- `seal` writes an append-only audit packet (raw observation window +
  manifest with a sha256) into the state directory; `verify` re-hashes it and
  fails on any mismatch. Tamper-evidence, not certification.
- `duplicates` hashes file contents locally with a size cap (`--size-cap`);
  over-cap and unreadable files are listed in `skipped`, never silently
  dropped.
- `casefile` writes `casefile.md` into the state directory: scope, inventory
  counts, observation chronology, duplicate groups and an explicit
  limitations section. It is file-level only — it does not read documents.
- `ask` runs Physis's model-free dialogue over the share's world. It only
  answers supported question shapes and prints refusals as refusals.
- `serve` replaces this process with `physis serve --stdio`, exposing the
  share's world to MCP clients. Read/write capabilities are whatever the
  Physis MCP surface allows; review before pointing an agent at it.

`document_inventory.py` is a companion module: extension-allowlist document
discovery with text extraction into a snapshot `corpus/` (binaries are
recorded as `unsupported_extraction` and never copied), symlinks never
followed, excluded directories counted, partial scans marked `incomplete`,
and an optional `bridge=True` that observes the root with Physis so
`search()` can map hits back to exact original paths.

## Safety and honesty

Only use a mount you are authorized to read. The share path must be an exact
mount point; `--allow-local` is intended only for local fixtures. State is
written outside the share in `~/.local/share/physis-nas/`, or choose another
location with `--state` before the command. Indexes may contain sensitive
filenames and content: secure the state directory and use exclusions.

The underlying scanner has limits and exclusions. Inspect `truncated` and
`skipped_files` in scan output: an absent result does not prove a file is
absent, and a successful scan does not prove every file was readable. Packet
verification proves the packet was not altered after sealing — it does not
prove the observations were true. `ask` refuses unsupported question shapes
instead of guessing. No file modifications on the share are intended, but
local state files are written. The mount-point check does not establish the
identity of the mounted device or share; do not re-use an index for a
different share.

## Tests

```sh
python3 -m unittest discover -v
```

12 tests: scan/search integration, change deltas, seal/verify round-trip and
tamper detection, duplicate grouping and skip reporting, casefile report,
refusal honesty, state-placement refusal, and the document inventory
(allowlist, symlinks, partial-scan safety, path-exact search mapping). The
integration tests use a temporary local fixture and the Physis binary path
shown above; they skip if that binary is absent. No actual NAS was tested.

## UGREEN connection

Candidate concept: an evidence-aware file guide that reports source
references and explicit gaps for selected NAS documents. This CLI is a
separate prototype, not part of the round-one package. UGREEN's permitted
tools, source access, citation capability, and privacy/data flow must be
verified before making claims about a Skill. The submitted Skill and core
workflow must comply with the contest's new-work and disclosure rules. No
registration or submission has been made.
