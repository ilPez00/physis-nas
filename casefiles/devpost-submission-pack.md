# Devpost submission pack — PHYSIS CASEFILES

Everything below is paste-ready. Register at ugreenhackathon.devpost.com,
create the submission, paste these answers, upload the two files, submit
BEFORE **Nov 15, 2026 11:45 PM PT** (= Nov 16, 08:45 CET).

## Uploads

1. `physis-casefiles-draft-v4.zip` — the Skill (5 files, 12.7 KB unpacked,
   official static checker: `static-pass`, 0 diagnostics).
2. `physis-casefiles-proposal.pdf` — this proposal, 2 pages.

Both are in this directory (`casefiles/`) and mirrored on air at
`/home/gio/hackmaxxing/physis-nas/casefiles/`.

## Project title

PHYSIS Casefiles

## Tagline (short pitch field)

From file investigator to an emerging cognitive system: a NAS Skill that
reconstructs what happened from a folder's own documents — and refuses to
fill gaps with a story.

## The ten questions

Paste each answer under its matching Devpost question. The full text lives
in `proposal.md` (sections 1–10); use it verbatim — it was written to the
official questions and checked for word count.

1. What does your Skill do? (one sentence) → proposal §1
2. Who is your target user, and what is their problem? → §2
3. What is your solution? → §3
4. What is the main user flow? → §4
5. How is your idea different from existing tools or common AI solutions? → §5
6. Which UGREEN AI NAS features does your Skill use, and at which step? → §6
7. What is your technical approach? → §7
8. What have you built so far? What is not built yet? What still needs
   testing on a NAS? → §8
9. How will you test your Skill if you become a Finalist? → §9
10. What are the known limits, risks, or outside dependencies? → §10

## If the form has extra fields

- **Inspiration**: forty documents hold the truth of a renovation dispute;
  nobody re-reads them, so the loudest memory wins. A NAS that reads them
  all — and reports what it cannot establish — changes that.
- **What it does**: see §1/§3.
- **How we built it**: a Markdown-only Skill over UGOS's registered agents
  (catalog v2.2.0), fixtures with a manual oracle, adversarial
  prompt-injection document, official static checker green (§7, §8).
- **Challenges**: honesty is the hard part — three evidence states, refusal
  to count copies as corroboration, absence reported as a finding.
- **Accomplishments**: zero-diagnostics static pass; a conflict case that
  reports a EUR 1,400 discrepancy instead of a fraud story.
- **What we learned**: absence, correctly reported, is the product.
- **What's next**: on-device testing of agent reasoning, approvals and
  returned locators (§8, §9).
- **Built with**: UGREEN UGOS registered agents (ug-filesystem, ug-document,
  ug-knowledge, ug-photo), Markdown Skill format, the official starter-kit
  checker.

## Mandatory disclosure

Somewhere visible in the submission (e.g. the "About"/credits field or the
end of an answer):

> Built with AI assistance (disclosed per contest rules). All claims about
> what is built are limited to the static artifacts listed in §8; nothing
> has run on a UGREEN device yet.

## Submission checklist

- [ ] Registered on Devpost (user account action)
- [ ] Title + tagline pasted
- [ ] Ten answers pasted from proposal.md
- [ ] ZIP v4 uploaded
- [ ] PDF uploaded
- [ ] AI-assistance disclosure pasted
- [ ] Submitted before Nov 15, 11:45 PM PT
- [ ] Screenshot of the submitted page saved to casefiles/
