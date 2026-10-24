---
name: update-profile
description: Refresh the kelu124 GitHub profile README — update star counts, surface new/recently active repos, sync the OSHWA-certified table and the papers list, flag dead or archived links, and propose wording changes. Use when asked to update, refresh, audit or tidy the GitHub profile / README in the kelu124/kelu124 repo.
---

# Update the GitHub profile README

## 0. Sync with GitHub first

The owner also edits README.md directly on github.com. Always `git fetch origin` and
merge `origin/main` before editing; when their edits land in an old spot, keep their
content but move it into the current layout (see CLAUDE.md).

## 1. Audit

```bash
python3 .claude/scripts/profile_audit.py            # human-readable
python3 .claude/scripts/profile_audit.py --json     # for scripting
python3 .claude/scripts/profile_audit.py --days 60  # narrow the "recent" window
```

It reports repos created since README.md was last committed, star badges that
break the rule (badge only if ≥ 20 stars, equal to the live count), linked repos
that vanished or were archived, and other recently pushed repos not mentioned.
Each run also appends star changes to `.claude/history/stars.csv`.

## 2. Apply — mechanical fixes (no need to ask)

- `python3 .claude/scripts/oshwa_sync.py` — refreshes the OSHWA-certified table.
- `python3 .claude/scripts/papers_sync.py` — refreshes the papers & publications list.
  Wrong/duplicate entry → add its DOI to `exclude` in `.claude/history/papers.json`;
  a work found elsewhere (e.g. Google Scholar, checked by hand) → add it to `include`;
  wrong section → set `"kind"` + `"kind_manual": true` on the work.
- `python3 .claude/scripts/profile_audit.py --fix` — sets/updates/removes `⭐ N`
  badges per the ≥ 20 rule.
- `python3 .claude/scripts/projects_sync.py --force --hook` — refreshes `projects/*.toml`
  (stars, forks, topics…) and rebuilds `projects/README.md`; the hook only does this
  monthly. New repos get a seeded file → use the `curate-projects` skill to write it up.
- Fix links to repos that were renamed (follow the API's redirect / new name).

## 3. Propose — editorial changes (ask first)

For each unlisted recent repo, suggest **where** it belongs and a one-line
description; let the user pick which ones go in. Rough mapping:

| Repo is about…                               | Section                             |
|----------------------------------------------|-------------------------------------|
| current ultrasound hardware                  | Ultrasound hardware (near the pic0rick callout) |
| Python libs / tools for probes or boards     | Ultrasound hardware → Software & libraries |
| FPGA, AI/ML, OSINT, data analysis, curated lists | Experimental, FPGA & AI         |
| superseded hardware                          | Past devices table (collapsible)    |
| planned / early-stage hardware               | Backlog                             |
| AI-agent experiments (Claude, NanoClaw)      | Experimental → "Experiments with Claude / NanoClaw" |
| polished games & toys (barcodebattler, pikl) | Fun                                 |
| quick sims / one-offs (5mins, FIFA2026…)     | usually skipped — ask               |

Also propose moving things that went quiet (no push in >1 year) toward
"Past devices", and archived repos out of active sections.
Before describing a repo, read its README (`curl -s https://raw.githubusercontent.com/kelu124/<repo>/HEAD/README.md`)
rather than relying on the one-line description alone.

## 4. Verify & commit

- Check the badges and stats images still render (URLs return 200).
- Show the user `git diff README.md` before committing; include the
  `.claude/history/` files (stars.csv, oshwa.json, papers.json) in the commit.
- Commit message: `autoupdate` for star/link-only refreshes, a descriptive
  message otherwise. Push when the user asks (they usually say "commit and push").
