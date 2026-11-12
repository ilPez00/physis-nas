# Kit and checker notes (milestone 1 artifact)

Recorded 2026-11-12 from the official starter kit `uliya-skill-kit-0.7.7-en.zip`
(downloaded from ai.ugreen.com/pages/hackathon-starter-kit; extracted at
`/tmp/uliya-skill-kit/`). The kit is UGREEN's material: it is NOT committed to
any repository. These notes record what we verified from it.

## Capability catalog

- Catalog version **2.2.0**, generated **2026-11-05** — newer than the v2.0.0
  (78 actions) described in the third-party guide; this kit ships **84 actions
  across 9 CLIs**.
- Invocation format: `cli.invoke --cli <CLI> --action <ACTION> -- <OPTIONS>`.
- CLI → registered expert mapping (from the kit's own checker, `check-lib.mjs`):
  ug-music → media-agent; ug-video → media-agent; ug-surveillance →
  security-monitor-agent; ug-filesystem → file-agent; ug-filemgr → file-agent;
  file-workflow → file-agent; ug-document → document-agent; ug-knowledge →
  knowledge-agent; ug-photo → photo-agent.
- Actions relevant to Casefiles (approval class in brackets):
  - ug-filesystem: find, ls, stat, category [none] — find supports path,
    pattern, type, date-type, start/end-timestamp, max-depth, limit, sort.
  - ug-document: extract [none], metadata, qa [none], page-count,
    **reconcile [none]** (options: file, max-files, query) — native read-only
    document comparison, no approval needed.
  - ug-photo: vision-ocr [none] (option: path), search-picture [none]
    (options include start-time/end-time, ocr-contains, file-name-contains),
    meta, timeline-summary [none]; timeline [workflow].
  - ug-knowledge: audio-transcription [workflow] (options: path, language,
    save, save-path), save-text [workflow] (options: content, content-ref,
    filename-hint, path), process-materials [none] — note: the standard doc
    says process-materials replaced collect-evidence and accepts only
    query/path/extension (not the old `full`).
- The standard doc warns that catalog examples are synthetic placeholders;
  the target environment's responses are authoritative.

## Checker contract (from scripts/check-lib.mjs, 667 lines)

What the official static checker enforces on a skill directory:

1. Frontmatter: only `name` and `description`, single-line plain values, both
   required, no duplicates, no complex YAML.
2. Required headings (regex): `# Goal` (or 目标), `# Required input`
   (必需输入), `# Workflow` or `# Orchestration` (专家编排), `# Failure
   handling` or `# Completion and failure` (完成与失败).
3. Five status tokens must appear in the source: `completed`, `failed`,
   `cancelled`, `waiting_user`, `waiting_approval`.
4. A generation-time capability evidence section headed exactly
   `# Generation-time capability evidence` (or 生成期能力依据), with one line
   per CLI in the form `` - `<cli>` → `<agent>` ``; each CLI at most once;
   the mapping must match the catalog's agent mapping above.
5. Every `delegate --target <agent>` target must be one of the six registered
   agents and must have corresponding CLI evidence in the section above.
6. Delegate command format: exactly one `--target` and one `--instruction`;
   no pipes, redirects, command substitution or extra flags; instruction
   non-empty.
7. Empty-result handling: if the skill mentions query/search/find/scan/
   filter/list/report intent, it must include empty-result language
   ("no results", "empty result") or a warning fires.
8. Forbidden patterns: private keys, credential assignments, curl/wget piped
   to shell, runtime code fences (bash/sh/python/js/ts/...), direct file APIs
   (readFile, writeFile, pathlib, fs., cp/mv/rm/cat, open()), HTTP calls
   (fetch/axios), NAS-style paths (/nas, /mnt, /volumeN, /shares), and
   bypass-approval language.
9. Placeholders (TODO, TBD, replace-with-, 待定) are flagged.
10. Packaging: ZIP ≤ 10 MB, ≤ 100 files, each file ≤ 1 MB; every
    `references/*.md` must be linked from SKILL.md; > 500 lines warns; no
    scripts or binaries — skills delegate to the registered agents.

Known trap: the kit's English template headings `# Capability evidence` and
`# Expert orchestration` fail its own checker — use the exact heading strings
above.

## Contest facts (verified from ugreenhackathon.devpost.com on 2026-11-12)

- Round 1 Submission: Oct 22 9:00 am PT – **Nov 15, 2026 11:45 pm PT**
  (= Nov 16, 08:45 CET). Round 1 judging Nov 16–19; finalist invitations
  Nov 21; Round 2 Nov 22–30; winners on or around Dec 6, 2026.
- Prize pool **$46,000**; Open Innovation track exists; Italy is on the
  eligible Europe list; individuals or teams of up to three.
- Round 1 deliverable: proposal PDF (ten answers, ≤ 500 words) + skill ZIP.
- The exact ten application questions are on the Devpost submission form
  (requires registration) — they must be transcribed from the form before the
  PDF is generated. Our proposal draft answers the known themes and is marked
  accordingly.
- Forum topics confirm open questions exist around image extraction, word
  limit, gateway approval scope and Photos timeline dates — check the
  discussions before finalizing any claim that depends on them.
