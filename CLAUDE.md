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
- `.claude/settings.json` — SessionStart hook runs the audit at startup; if it prints
  anything, tell the user and offer the `update-profile` skill.
- `.claude/skills/update-profile/` — the refresh workflow.

## README conventions

- Repo entries: `- **[name](https://github.com/kelu124/name)** ⭐ N - short description`.
  **Show `⭐ N` only when the repo has ≥ 20 stars** (`MIN_STARS` in the script), and keep
  it equal to the live count. Below 20, no badge. The script parses this exact pattern.
- Structure: centered header + badge row → About me (+ links table) → Ultrasound hardware
  (flagship callout, software, collapsible Past devices table, Backlog) →
  Experimental, FPGA & AI → Stats.
- Voice: first person, casual, light emoji, a wink here and there ";)". Don't
  polish it into corporate prose; keep the owner's phrasing when editing.
- Ultrasound hardware is the core identity — pic0rick is the current flagship;
  newer boards (e.g. ultr4rick, minus) should be placed relative to it.

## Rules

- Star-badge and broken-link fixes: just do them.
- Adding/removing/moving projects or rewording the bio: propose, then wait for OK.
- Never push without being asked. Refresh-only commits use the message `autoupdate`.
