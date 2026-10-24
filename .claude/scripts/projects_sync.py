#!/usr/bin/env python3
"""Keep projects/*.toml in sync with kelu124's public GitHub repositories.

One TOML file per original (non-fork) public repo, plus projects/forks.toml for the
forks. Each file has two parts:

  * GitHub-managed fields (name, url, description, license, topics, stars, forks, ...)
    — rewritten on every sync.
  * Curated fields (category, summary, keywords, tags, plus anything else you add)
    — never touched by the script once present. New repos get seeded values and
    curated = false so the hook can ask for a proper write-up.

`tags` are chips / platforms / EDA tools (rp2040, ch569, pic32, ecp5, up5k, hx4k, hx8k,
esp32, raspberry-pi, kicad, ...) — not domain words, those go in `keywords`. Seeding
scans name + description + topics + README for them (see CHIP_TAGS) and is only a
starting point: it over-tags, so check it by hand. `keywords` start from the repo topics.

After syncing, projects/README.md is rebuilt by projects_readme.py.

Usage:
  python3 .claude/scripts/projects_sync.py            # sync now, report
  python3 .claude/scripts/projects_sync.py --check    # report only, write nothing
  python3 .claude/scripts/projects_sync.py --hook     # SessionStart: runs only if the
                                                      # last sync is >= 30 days old,
                                                      # quiet when offline
  python3 .claude/scripts/projects_sync.py --force    # ignore the 30-day gate (with --hook)

Stdlib only (Python >= 3.11 for tomllib). Set GITHUB_TOKEN to raise the 60 req/h
anonymous API limit; READMEs come from raw.githubusercontent.com (not rate-limited).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projects_readme  # noqa: E402

USER = "kelu124"
ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "projects"
FORKS = PROJECTS / "forks.toml"
STATE = ROOT / ".claude" / "history" / "projects_sync.json"
MIN_DAYS = 30

MANAGED = ["name", "url", "description", "homepage", "license", "language", "topics",
           "stars", "forks", "watchers", "open_issues", "created", "pushed", "archived",
           "default_branch", "fetched"]
CURATED = ["category", "summary", "keywords", "tags", "curated"]

# tag -> regex matched (case-insensitively) against name, description, topics and README
CHIP_TAGS = {
    "rp2040": r"rp2040|raspberry\s*pi\s*pico|\bpico\b|pic0",
    "rp2350": r"rp2350",
    "ch569": r"ch569|ch56x",
    "pic32": r"pic32",
    "ecp5": r"ecp5|ulx3s|orangecrab|colorlight",
    "up5k": r"up5k|upduino|ice40\s*ultra\s*plus|ultraplus",
    "hx4k": r"hx4k",
    "hx8k": r"hx8k",
    "ice40": r"ice40|icestorm|icestick",
    "fpga": r"\bfpga\b|verilog|yosys|nextpnr",
    "esp32": r"esp32",
    "esp8266": r"esp8266",
    "attiny": r"attiny",
    "arduino": r"arduino",
    "stm32": r"stm32",
    "raspberry-pi": r"raspberry\s*pi(?!\s*pico)|\bphat\b|\brpi\b",
    "beaglebone": r"beaglebone",
    "redpitaya": r"red\s*pitaya",
    "ftdi": r"\bft(600|601|2232|232|4222)\b|\bftdi\b",
    "max14866": r"max14866",
    "ad8332": r"ad8332",
    "hv9150": r"hv9150",
    "drv8662": r"drv8662",
    "lm3478": r"lm3478",
    "dac2932": r"dac2932",
    "adc08200": r"adc08200",
    "ad9629": r"ad9629",
    "tdc7200": r"tdc7200|tdc7k",
    "nsa1166": r"nsa1166",
    "kicad": r"kicad",
    "altium": r"altium",
    "micropython": r"micropython",
}


# ---------------------------------------------------------------- GitHub

def headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "kelu124-projects-sync"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return h


def fetch_repos(timeout):
    repos, page = [], 1
    while True:
        url = f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&sort=full_name"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers()), timeout=timeout) as r:
            batch = json.load(r)
        if not batch:
            return repos
        repos.extend(batch)
        page += 1


def fetch_readme(repo, timeout=15):
    for fn in ("README.md", "readme.md", "README.rst", "README", "Readme.md", "README.markdown", "README.txt"):
        url = f"https://raw.githubusercontent.com/{USER}/{repo['name']}/{repo['default_branch']}/{fn}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kelu124-projects-sync"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------- TOML I/O

def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if v is None:
        return '""'
    raise TypeError(f"unsupported TOML value: {v!r}")


def dump_project(d):
    lines = [f"# {d['name']} — managed by .claude/scripts/projects_sync.py",
             "# Fields down to `fetched` are refreshed from GitHub; the rest is hand-curated and kept."]
    for k in MANAGED:
        lines.append(f"{k} = {toml_value(d.get(k))}")
    lines.append("")
    for k in CURATED:
        if k in d:
            lines.append(f"{k} = {toml_value(d[k])}")
    for k, v in d.items():
        if k not in MANAGED and k not in CURATED:
            lines.append(f"{k} = {toml_value(v)}")
    return "\n".join(lines) + "\n"


def load_projects():
    out = {}
    for f in sorted(PROJECTS.glob("*.toml")):
        if f.name == FORKS.name:
            continue
        with f.open("rb") as h:
            out[f.stem] = tomllib.load(h)
    return out


def managed_fields(r, today):
    return {
        "name": r["name"],
        "url": r["html_url"],
        "description": r["description"] or "",
        "homepage": r["homepage"] or "",
        "license": (r.get("license") or {}).get("spdx_id") or "",
        "language": r["language"] or "",
        "topics": sorted(r.get("topics") or []),
        "stars": r["stargazers_count"],
        "forks": r["forks_count"],
        "watchers": r["subscribers_count"] if "subscribers_count" in r else r["watchers_count"],
        "open_issues": r["open_issues_count"],
        "created": r["created_at"][:10],
        "pushed": (r["pushed_at"] or "")[:10],
        "archived": bool(r["archived"]),
        "default_branch": r["default_branch"],
        "fetched": today,
    }


def seed_curated(r, readme):
    blob = " ".join([r["name"], r["description"] or "", " ".join(r.get("topics") or []), readme[:20000]])
    tags = [t for t, rx in CHIP_TAGS.items() if re.search(rx, blob, re.I)]
    return {
        "category": "other",
        "summary": r["description"] or "",
        "keywords": sorted(r.get("topics") or []),
        "tags": tags,
        "curated": False,
    }


def dump_forks(forks, today):
    lines = ["# Forks of other people's repositories — fully managed by .claude/scripts/projects_sync.py",
             f'fetched = "{today}"', ""]
    for r in sorted(forks, key=lambda r: r["name"].lower()):
        lines += ["[[fork]]",
                  f"name = {toml_value(r['name'])}",
                  f"url = {toml_value(r['html_url'])}",
                  f"description = {toml_value(r['description'] or '')}",
                  f"language = {toml_value(r['language'] or '')}",
                  f"stars = {r['stargazers_count']}",
                  f"pushed = {toml_value((r['pushed_at'] or '')[:10])}",
                  ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--hook", action="store_true", help="terse SessionStart mode with the monthly gate")
    ap.add_argument("--force", action="store_true", help="ignore the monthly gate")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    state = load_state()
    if args.hook and not args.force:
        last = state.get("last_sync")
        if last and (dt.date.today() - dt.date.fromisoformat(last)).days < MIN_DAYS:
            return

    try:
        repos = fetch_repos(timeout=10 if args.hook else 30)
    except Exception as e:
        if args.hook:
            return  # offline / rate-limited: retry next session
        sys.exit(f"GitHub API error: {e}")

    PROJECTS.mkdir(exist_ok=True)
    existing = load_projects()
    originals = [r for r in repos if not r["fork"]]
    forks = [r for r in repos if r["fork"]]
    live = {r["name"] for r in originals}

    new, updated, star_moves = [], [], []
    for r in originals:
        old = existing.get(r["name"])
        d = managed_fields(r, today)
        if old is None:
            d.update(seed_curated(r, fetch_readme(r)))
            new.append(r["name"])
        else:
            for k, v in old.items():
                if k not in MANAGED:
                    d[k] = v
            diff = [k for k in MANAGED if k != "fetched" and old.get(k) != d[k]]
            if diff:
                updated.append((r["name"], diff))
                if "stars" in diff:
                    star_moves.append((r["name"], old.get("stars", 0), d["stars"]))
        if not args.check:
            (PROJECTS / f"{r['name']}.toml").write_text(dump_project(d))

    gone = sorted(n for n in existing if n not in live)  # deleted, made private, or became a fork
    if not args.check:
        FORKS.write_text(dump_forks(forks, today))
        projects_readme.build()
        STATE.parent.mkdir(parents=True, exist_ok=True)
        state.update(last_sync=today, originals=len(originals), forks=len(forks), new=new, gone=gone)
        STATE.write_text(json.dumps(state, indent=2) + "\n")

    if args.hook:
        if not (new or gone or updated):
            return
        print("[kelu124 projects catalogue synced — mention this to the user; "
              "new entries need a hand-written summary/keywords/tags/category, then commit]")
        if new:
            print("New project files seeded (curated = false): " + ", ".join(f"projects/{n}.toml" for n in new))
        if gone:
            print("Repos no longer public (file kept, delete by hand if wanted): " + ", ".join(gone))
        if star_moves:
            print("Star changes: " + ", ".join(f"{n} {b - a:+d} (⭐{b})" for n, a, b in
                                              sorted(star_moves, key=lambda m: m[1] - m[2])))
        print(f"{len(updated)} files refreshed, projects/README.md rebuilt.")
        return

    verb = "Would write" if args.check else "Wrote"
    print(f"{verb} {len(originals)} project files + forks.toml ({len(forks)} forks) in {PROJECTS.relative_to(ROOT)}/")
    print(f"  new: {len(new)}" + (" — " + ", ".join(new) if new else ""))
    print(f"  changed: {len(updated)}")
    for n, diff in updated:
        print(f"    {n}: {', '.join(diff)}")
    if gone:
        print(f"  no longer public: {', '.join(gone)}")
    uncurated = [n for n, d in existing.items() if not d.get("curated", True)] + new
    if uncurated:
        print(f"  awaiting curation: {', '.join(sorted(set(uncurated)))}")


if __name__ == "__main__":
    main()
