# kelu124/kelu124 — GitHub profile README

This repo is the special profile repo: `README.md` is rendered on
https://github.com/kelu124. Claude's job here is to keep it reasonably up to date.

## Layout

- `README.md` — the only published content.
- `.claude/scripts/profile_audit.py` — compares README against live GitHub data:
  new repos since the last README commit, star-badge drift, dead/archived links.
  `--fix` rewrites star badges; `--hook` is the terse SessionStart mode. Stdlib only;
  set `GITHUB_TOKEN` if the 60 req/h anonymous limit bites. `gh` is not installed.
- `.claude/history/stars.csv` — star history (`date,repo,stars,delta`), appended by
  every audit run, only for repos whose count changed. Commit it with README updates.
- `.claude/settings.json` — SessionStart hooks run the audit, the OSHWA sync, the papers sync
  and the (monthly) projects catalogue sync at startup; if they print anything, tell the
  user (offer the `update-profile` / `curate-projects` skill / a commit).
- `.claude/scripts/oshwa_sync.py` — rewrites the OSHWA-certified table between
  `<!-- OSHWA:START -->` / `<!-- OSHWA:END -->` (designs by Luc Jonveaux / kelu124).
  Uses the OSHWA API if a token is in `$OSHWA_TOKEN` or `.claude/oshwa_token` (gitignored),
  else the public directory page. If both fail, or the markers are removed, the table is
  left alone for manual editing. Cache + repo-link overrides: `.claude/history/oshwa.json`.
- `.claude/scripts/papers_sync.py` — rewrites the papers list between `<!-- PAPERS:START -->` /
  `<!-- PAPERS:END -->` from DOIs found via ORCID (0000-0001-9003-4930), Crossref and DataCite
  (Zenodo, arXiv). Filters out other Jonveaux authors. Cache, `exclude` list and manual `kind`
  overrides: `.claude/history/papers.json`. DOIs once found stay listed unless excluded.
  Google Scholar (https://scholar.google.com/citations?user=PbsXAhYAAAAJ) has no API and blocks
  bots, so it's not in the hook: cross-check it by hand now and then and add missing DOIs to
  `include`. Last check 2026-10-22: all DOI works covered; the Vanderbilt 2017 report has no DOI;
  the "Materials and Acoustics Handbook" there is a Scholar misattribution (not Luc's).
- `projects/` — the projects catalogue: one `<repo>.toml` per original public repo
  (GitHub-managed fields first, then hand-curated `category`, `summary`, `keywords`,
  `tags`, `curated`), `forks.toml` for the forks, and a generated `README.md`.
  `.claude/scripts/projects_sync.py` refreshes the managed fields, seeds files for new
  repos (`curated = false`) and rebuilds the README via `.claude/scripts/projects_readme.py`.
  The SessionStart hook runs it only when `.claude/history/projects_sync.json` says the
  last sync is ≥ 30 days old (`--force` to override). `tags` = chips / platforms / EDA
  tools only (rp2040, rp2350, ch569, pic32, ecp5, up5k, hx4k, hx8k, ice40, esp32, attiny,
  raspberry-pi, kicad, altium…); domain words go in `keywords`; `topics` are GitHub's.
  Curating a new entry = the `curate-projects` skill.
- `.claude/skills/update-profile/` — the refresh workflow.
- `.claude/skills/curate-projects/` — writing summaries/keywords/tags for new catalogue entries.

## README conventions

- Repo entries: `- **[name](https://github.com/kelu124/name)** ⭐ N - short description`.
  **Show `⭐ N` only when the repo has ≥ 20 stars** (`MIN_STARS` in the script), and keep
  it equal to the live count. Below 20, no badge. The script parses this exact pattern.
- Structure: centered header + badge row → About me (+ links table) → Ultrasound hardware
  (flagship callout, in the works, software, collapsible Past devices table, Backlog) →
  OSHWA-certified (generated table) → Experimental, FPGA & AI → Fun → Papers & publications
  (generated) → Stats.
- Header badges: LinkedIn, Hackaday, Substack, website, Matrix chat (#un0rick-general). No donation badges.
- Voice: first person, casual, light emoji, a wink here and there ";)". Don't
  polish it into corporate prose; keep the owner's phrasing when editing.
- Ultrasound hardware is the core identity — pic0rick is the current flagship;
  newer boards (e.g. ultr4rick, minus) should be placed relative to it.

## Rules

- Star-badge and broken-link fixes: just do them.
- Adding/removing/moving projects or rewording the bio: propose, then wait for OK.
- Never push without being asked. Refresh-only commits use the message `autoupdate`.
