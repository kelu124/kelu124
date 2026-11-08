#!/usr/bin/env python3
"""Track stars, forks and watchers over time, one file per original public repo.

projects/tracker/<repo>.json is a list of rows sorted by date, oldest first:

  [
    {"date": "2026-11-08", "stars": 117, "forks": 27, "watchers": 8}
  ]

A row is added only when a count changed, so a gap between two dates means nothing
moved. There is at most one row per date.

`watchers` is GitHub's real watcher count (subscribers_count). The repo listing doesn't
include it (its watchers_count is just the stars again), so it costs one API call per
repo. Each run spends what the rate limit can spare, never-checked repos first (highest
stars first), then the longest unchecked. Until a repo has been checked its value is
null. Set GITHUB_TOKEN to check everything in one go.

Usage:
  python3 .claude/scripts/projects_tracker.py          # run now, report
  python3 .claude/scripts/projects_tracker.py --hook   # SessionStart: once a day, or
                                                       # again while watchers are missing

Stdlib only. Check dates are kept in .claude/history/projects_tracker.json.
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from projects_sync import PROJECTS, ROOT, USER, fetch_repos, headers  # noqa: E402

TRACKER = PROJECTS / "tracker"
STATE = ROOT / ".claude" / "history" / "projects_tracker.json"
RESERVE = 15       # API calls left for the other SessionStart hooks and manual use
MAX_SECONDS = 90   # stay inside the hook timeout


def get_json(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers()), timeout=timeout) as r:
        return json.load(r)


def spare_calls():
    try:  # this endpoint doesn't count against the limit
        return max(0, get_json("https://api.github.com/rate_limit")["resources"]["core"]["remaining"] - RESERVE)
    except Exception:
        return 0


def fetch_watchers(repos, checked, today):
    """Real watcher counts for as many repos as the rate limit allows."""
    todo = sorted((r for r in repos if checked.get(r["name"]) != today),
                  key=lambda r: (checked.get(r["name"], ""), -r["stargazers_count"]))
    found, deadline = {}, time.monotonic() + MAX_SECONDS
    for r in todo[:spare_calls()]:
        if time.monotonic() > deadline:
            break
        try:
            found[r["name"]] = get_json(f"https://api.github.com/repos/{USER}/{r['name']}")["subscribers_count"]
        except Exception:
            break  # offline or rate-limited: the rest waits for the next run
    return found


def load_rows(name):
    try:
        return json.loads((TRACKER / f"{name}.json").read_text())
    except (OSError, ValueError):
        return []


def dump_rows(rows):
    body = ",\n".join("  " + json.dumps(r) for r in sorted(rows, key=lambda r: r["date"]))
    return f"[\n{body}\n]\n"


def update_rows(rows, repo, watchers, today):
    """Apply today's counts to a history. Returns True if it changed."""
    last = rows[-1] if rows else None
    changed = False
    if watchers is None and last:
        watchers = last["watchers"]
    elif last and last["watchers"] is None and watchers is not None:
        last["watchers"] = watchers  # first real value for a row that was waiting on it
        changed = True
    row = {"date": today, "stars": repo["stargazers_count"], "forks": repo["forks_count"], "watchers": watchers}
    if last and all(last[k] == row[k] for k in ("stars", "forks", "watchers")):
        return changed
    if last and last["date"] == today:
        rows[-1] = row
    else:
        rows.append(row)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hook", action="store_true", help="terse SessionStart mode, gated to once a day")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    if args.hook and state.get("last_run") == today and not state.get("watchers_missing"):
        return

    try:
        repos = [r for r in fetch_repos(timeout=10 if args.hook else 30) if not r["fork"]]
    except Exception as e:
        if args.hook:
            return  # offline / rate-limited: retry next session
        sys.exit(f"GitHub API error: {e}")

    checked = state.get("watchers_checked", {})
    found = fetch_watchers(repos, checked, today)
    checked.update((name, today) for name in found)

    TRACKER.mkdir(parents=True, exist_ok=True)
    changed, missing = [], 0
    for r in repos:
        rows = load_rows(r["name"])
        if update_rows(rows, r, found.get(r["name"]), today):
            (TRACKER / f"{r['name']}.json").write_text(dump_rows(rows))
            changed.append(r["name"])
        missing += rows[-1]["watchers"] is None

    STATE.write_text(json.dumps({"last_run": today, "watchers_missing": missing,
                                 "watchers_checked": dict(sorted(checked.items()))}, indent=2) + "\n")

    if not args.hook:
        print(f"{len(repos)} projects tracked, {len(changed)} files updated, "
              f"{len(found)} watcher counts checked, {missing} still unknown.")
    elif changed:
        print(f"[kelu124 tracker] {len(changed)} of projects/tracker/*.json updated"
              + (f", {missing} watcher counts still to fetch" if missing else "") + " — commit when convenient.")


if __name__ == "__main__":
    main()
