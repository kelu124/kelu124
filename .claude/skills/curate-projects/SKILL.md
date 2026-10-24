---
name: curate-projects
description: Write or refresh the hand-curated part (category, summary, keywords, tags) of entries in the kelu124 projects catalogue (projects/*.toml) and rebuild projects/README.md. Use when the projects sync hook reports new seeded files (curated = false), when asked to describe/tag/categorise repos in the catalogue, or to re-sync the catalogue by hand.
---

# Curate the projects catalogue

`projects/<repo>.toml` has GitHub-managed fields (down to `fetched`, rewritten by
`.claude/scripts/projects_sync.py`) and curated fields that the script never touches:
`category`, `summary`, `keywords`, `tags`, `curated`.

## 1. Find what needs work

```bash
python3 .claude/scripts/projects_sync.py --check          # lists "awaiting curation"
grep -l 'curated = false' projects/*.toml
python3 .claude/scripts/projects_sync.py --force --hook   # re-sync now, ignoring the 30-day gate
```

## 2. Read the repo before writing

```bash
curl -s https://raw.githubusercontent.com/kelu124/<repo>/HEAD/README.md | head -120
```
The one-line GitHub description is not enough. If the README is empty, say so in the
summary ("placeholder", "no README") rather than inventing content.

## 3. Fill the curated fields

- `category` — one of: `ultrasound-hardware`, `ultrasound-software`, `ultrasound-research`,
  `hardware`, `fpga`, `ai`, `data`, `web`, `fun`, `meta`, `other`
  (titles/blurbs in `projects_readme.py` `CATEGORIES`; add a new one there if really needed).
- `summary` — one paragraph, 1–4 sentences, owner's casual first-person-ish voice (see
  CLAUDE.md "Voice"), concrete: chips, sample rates, what it does, status (early design,
  superseded, OSHWA certified…). Mention the sibling board it relates to (pic0rick is the flagship).
- `keywords` — generated topical words, lowercase, 4–9 of them. Don't repeat `topics`
  (GitHub's own) verbatim; complement them.
- `tags` — chips / platforms / EDA tools only, lowercase, from the vocabulary in
  `projects_sync.py` `CHIP_TAGS` (`rp2040`, `rp2350`, `ch569`, `pic32`, `ecp5`, `up5k`, `hx4k`,
  `hx8k`, `ice40`, `fpga`, `esp32`, `attiny`, `arduino`, `raspberry-pi`, `beaglebone`,
  `redpitaya`, `ftdi`, `max14866`, `ad8332`, `kicad`, `altium`, `micropython`…). The seeded
  list over-tags (regex over the README): prune it. No languages (`language` already says so),
  no domain words (those are keywords). Empty list is fine for pure software.
- `curated = true` once done.

Edit the TOML directly (strings are JSON-style double-quoted; arrays of strings).

## 4. Rebuild and verify

```bash
python3 .claude/scripts/projects_readme.py
python3 -c "import tomllib,glob;[tomllib.load(open(f,'rb')) for f in glob.glob('projects/*.toml')]"
```
Then `git diff --stat projects/` and offer a commit (message: `Curate projects catalogue: <repos>`;
a pure re-sync with no hand edits is `autoupdate`). Never push without being asked.

## Removed / private repos

The sync keeps the file and reports "no longer public". Delete the TOML by hand if the
repo is really gone, keep it if it's a temporary private flip.
