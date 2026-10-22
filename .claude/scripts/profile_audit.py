#!/usr/bin/env python3
"""Audit README.md against live GitHub data for the kelu124 profile.

Reports:
  1. New public repos created since README.md was last committed, not yet listed.
  2. Star badges (⭐ N) out of line with the rule: shown only when live stars >= MIN_STARS,
     and always matching the live count.
  3. Links in README pointing to kelu124 repos that no longer exist / are archived.
  4. Recently pushed non-fork repos not mentioned in README (full mode only).

Every run also records star changes in .claude/history/stars.csv
(date,repo,stars,delta — one row per repo whose count changed since its last row;
the first run is the baseline, delta = stars).

Stdlib only. Uses the public GitHub API (60 req/h unauthenticated);
set GITHUB_TOKEN to raise the limit.

Usage:
  python3 .claude/scripts/profile_audit.py [--days 120] [--json]
  python3 .claude/scripts/profile_audit.py --fix    # rewrite star badges in README.md
  python3 .claude/scripts/profile_audit.py --hook   # terse, silent when clean/offline (SessionStart)
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

USER = "kelu124"
MIN_STARS = 20
ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
HISTORY = ROOT / ".claude" / "history" / "stars.csv"

# "**[name](url)**" optionally followed by " ⭐ N"
ENTRY_RE = re.compile(r"(\*\*\[([^\]]+)\]\([^)]*\)\*\*)(\s*⭐\s*(\d+))?")


def fetch_repos(timeout):
    repos, page = [], 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-audit"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    while True:
        url = f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&sort=pushed"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            batch = json.load(r)
        if not batch:
            return repos
        repos.extend(batch)
        page += 1


def readme_last_commit():
    out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", "README.md"],
                         cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return dt.datetime.fromisoformat(out) if out else None


def record_history(repos):
    """Append rows for repos whose star count changed; return today's [(name, stars, delta)]."""
    last = {}
    if HISTORY.exists():
        for line in HISTORY.read_text().splitlines()[1:]:
            _, name, stars, _ = line.split(",")
            last[name] = int(stars)
    today = dt.date.today().isoformat()
    rows = []
    for r in sorted(repos.values(), key=lambda r: r["name"].lower()):
        if r["fork"]:
            continue
        n, prev = r["stargazers_count"], last.get(r["name"])
        if prev != n and (prev is not None or n > 0):
            rows.append((r["name"], n, n - (prev or 0)))
    if rows:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        new_file = not HISTORY.exists()
        with HISTORY.open("a") as f:
            if new_file:
                f.write("date,repo,stars,delta\n")
            f.writelines(f"{today},{name},{n},{d}\n" for name, n, d in rows)
    return rows, not last


def parse_date(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def star_issues(text, repos):
    """Return [(name, readme_stars_or_None, live_stars)] for entries breaking the badge rule."""
    issues = []
    for m in ENTRY_RE.finditer(text):
        name, claimed = m.group(2), m.group(4)
        live = repos.get(name.lower())
        if not live:
            continue
        n = live["stargazers_count"]
        want = n if n >= MIN_STARS else None
        have = int(claimed) if claimed else None
        if want != have:
            issues.append((name, have, n))
    return issues


def fix_badges(text, repos):
    def repl(m):
        live = repos.get(m.group(2).lower())
        if not live:
            return m.group(0)
        n = live["stargazers_count"]
        return f"{m.group(1)} ⭐ {n}" if n >= MIN_STARS else m.group(1)
    return ENTRY_RE.sub(repl, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120, help="'recent' window for unlisted repos")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fix", action="store_true", help="rewrite star badges in README.md")
    ap.add_argument("--hook", action="store_true", help="terse output for the SessionStart hook")
    args = ap.parse_args()

    try:
        repos = {r["name"].lower(): r for r in fetch_repos(timeout=8 if args.hook else 30)}
    except Exception as e:
        if args.hook:
            return  # offline / rate-limited: stay quiet at session start
        sys.exit(f"GitHub API error: {e}")

    changes, baseline = record_history(repos)
    text = README.read_text()

    if args.fix:
        new = fix_badges(text, repos)
        if new != text:
            README.write_text(new)
        print(f"Star badges updated ({len(star_issues(text, repos))} changed).")
        return

    linked = {m.lower() for m in re.findall(rf"github\.com/{USER}/([A-Za-z0-9_.-]+)", text)}
    linked.discard(USER.lower())
    own = [r for r in repos.values() if not r["fork"] and r["name"].lower() != USER.lower()]

    since = readme_last_commit()
    new_repos = sorted(
        (r for r in own if r["name"].lower() not in linked and since and parse_date(r["created_at"]) > since),
        key=lambda r: r["created_at"], reverse=True)

    badges = star_issues(text, repos)
    missing = sorted(n for n in linked if n not in repos)
    archived = sorted(n for n in linked if n in repos and repos[n]["archived"])

    # Plain (non-bold) links to repos popular enough to deserve an entry with a badge
    bold = {m.group(2).lower() for m in ENTRY_RE.finditer(text)}
    popular_plain = sorted((repos[n] for n in linked if n in repos and n not in bold
                            and repos[n]["stargazers_count"] >= MIN_STARS),
                           key=lambda r: -r["stargazers_count"])

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    new_names = {r["name"] for r in new_repos}
    unlisted = sorted(
        (r for r in own if r["name"].lower() not in linked and r["name"] not in new_names
         and parse_date(r["pushed_at"]) >= cutoff),
        key=lambda r: r["pushed_at"], reverse=True)

    def fmt_badge(n, have, live):
        if have is None:
            return f"{n}: add ⭐ {live}"
        if live < MIN_STARS:
            return f"{n}: drop badge (⭐{have} -> {live}, below {MIN_STARS})"
        return f"{n}: ⭐{have} -> ⭐{live}"

    if args.hook:
        lines = []
        if new_repos:
            lines.append(f"New repos since README last updated ({since:%Y-%m-%d}):")
            lines += [f"  - {r['name']} (⭐{r['stargazers_count']}, created {r['created_at'][:10]}) — "
                      f"{r['description'] or 'no description'}" for r in new_repos]
        if badges:
            lines.append("Star badges to fix: " + "; ".join(fmt_badge(*b) for b in badges))
        if missing or archived:
            lines.append(f"Dead/archived links: {', '.join(missing + archived)}")
        if changes and not baseline:
            lines.append("Star changes since last check: " + ", ".join(
                f"{n} {d:+d} (⭐{s})" for n, s, d in sorted(changes, key=lambda c: -c[2])))
        if lines:
            print("[kelu124 profile audit — mention this to the user and offer to run the update-profile skill]")
            print("\n".join(lines))
        return

    if args.json:
        json.dump({
            "readme_last_commit": since.isoformat() if since else None,
            "new_since_readme": [dict(name=r["name"], stars=r["stargazers_count"], created=r["created_at"][:10],
                                      description=r["description"], language=r["language"],
                                      topics=r.get("topics", [])) for r in new_repos],
            "badge_issues": [dict(name=n, readme=a, live=b) for n, a, b in badges],
            "missing_or_private": missing,
            "archived": archived,
            "popular_plain_links": [dict(name=r["name"], stars=r["stargazers_count"]) for r in popular_plain],
            "unlisted_recent": [dict(name=r["name"], stars=r["stargazers_count"], pushed=r["pushed_at"][:10],
                                     description=r["description"]) for r in unlisted],
        }, sys.stdout, indent=2, ensure_ascii=False)
        return

    if changes:
        label = "Baseline recorded" if baseline else "Star changes since last check"
        print(f"## {label} ({len(changes)} repos) -> {HISTORY.relative_to(ROOT)}")
        if not baseline:
            for n, st, d in sorted(changes, key=lambda c: -c[2]):
                print(f"  {d:+d}  {n} (⭐{st})")
        print()
    print(f"## New repos since README last updated ({since:%Y-%m-%d}) ({len(new_repos)})")
    for r in new_repos:
        print(f"  {r['created_at'][:10]} ⭐{r['stargazers_count']:<4} {r['name']} — {r['description'] or '(no description)'}")
    print(f"\n## Star badge issues (rule: show only if >= {MIN_STARS}) ({len(badges)})")
    for b in badges:
        print("  " + fmt_badge(*b))
    print(f"\n## Linked repos not found publicly ({len(missing)})")
    for n in missing:
        print(f"  {n}")
    print(f"\n## Linked repos now archived ({len(archived)})")
    for n in archived:
        print(f"  {n}")
    print(f"\n## Plain links to repos with >= {MIN_STARS} stars (no badge entry) ({len(popular_plain)})")
    for r in popular_plain:
        print(f"  ⭐{r['stargazers_count']:<4} {r['name']}")
    print(f"\n## Other repos pushed in last {args.days}d, not in README ({len(unlisted)})")
    for r in unlisted:
        print(f"  {r['pushed_at'][:10]} ⭐{r['stargazers_count']:<4} {r['name']} — {r['description'] or '(no description)'}")


if __name__ == "__main__":
    main()
