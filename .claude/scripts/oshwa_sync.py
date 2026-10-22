#!/usr/bin/env python3
"""Keep the OSHWA-certified projects table in README.md in sync.

Looks up certified designs by Luc Jonveaux / kelu124 and rewrites the table between
<!-- OSHWA:START --> and <!-- OSHWA:END --> in README.md.

Sources, in order:
  1. OSHWA certification API (https://certificationapi.oshwa.org/open-api-spec) —
     needs a token in $OSHWA_TOKEN or .claude/oshwa_token (gitignored).
  2. The public directory page https://certification.oshwa.org/list.html (no token).
If both fail (offline, API deprecated, page changed), README is left untouched, so
the table can still be maintained by hand. Missing markers also mean "hands off".

Fetched projects are cached in .claude/history/oshwa.json (detail pages are only
fetched once per certification). A "repo" set there wins over what OSHWA lists, so
links can be corrected by hand.

Usage:
  python3 .claude/scripts/oshwa_sync.py          # sync and report
  python3 .claude/scripts/oshwa_sync.py --check  # report only, don't write
  python3 .claude/scripts/oshwa_sync.py --hook   # terse; silent when nothing changed
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CACHE = ROOT / ".claude" / "history" / "oshwa.json"
TOKEN_FILE = ROOT / ".claude" / "oshwa_token"
API = "https://certificationapi.oshwa.org/api/projects"
DIRECTORY = "https://certification.oshwa.org"
MATCH = re.compile(r"jonveaux|kelu124", re.I)
START, END = "<!-- OSHWA:START -->", "<!-- OSHWA:END -->"


def get(url, timeout, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "kelu124-profile", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def pick_repo(urls):
    urls = [u for u in urls if u]
    gh = [u for u in urls if "github.com/kelu124/" in u.lower()]
    return (gh or urls or [None])[0]


def from_api(token, timeout, cache):
    found = {}
    for q in ("Jonveaux", "kelu124"):
        url = f"{API}?{urllib.parse.urlencode({'q': q, 'limit': 1000})}"
        data = json.loads(get(url, timeout, {"Authorization": f"Bearer {token}"}))
        for p in data.get("items", []):
            blob = " ".join(str(p.get(k, "")) for k in
                            ("responsibleParty", "publicContact", "projectWebsite", "documentationUrl"))
            if not MATCH.search(blob):
                continue
            found[p["oshwaUid"].upper()] = {
                "uid": p["oshwaUid"].upper(),
                "name": p["projectName"],
                "date": (p.get("certificationDate") or "")[:10],
                "hardware": p.get("hardwareLicense") or "",
                "repo": cache.get(p["oshwaUid"].upper(), {}).get("repo")
                        or pick_repo([p.get("documentationUrl"), p.get("projectWebsite")]),
            }
    return found


def from_directory(timeout, cache):
    html = get(f"{DIRECTORY}/list.html", timeout)
    rows = re.findall(r'<tr class="project">(.*?)</tr>', html, re.S)
    if not rows:
        raise ValueError("directory layout changed")

    def cell(row, cls):
        m = re.search(rf'class="{cls}[^"]*"[^>]*>(.*?)</td>', row, re.S)
        return m.group(1).strip() if m else ""

    found = {}
    for row in rows:
        if not MATCH.search(cell(row, "responsible-party") + cell(row, "keywords")):
            continue
        uid = cell(row, "uid").upper()
        name = re.search(r'class="name"[^>]*>([^<]+)</a>', row).group(1).strip()
        date = re.search(r'date="(\d{4}-\d{2}-\d{2})', row)
        repo = cache.get(uid, {}).get("repo")
        if repo is None:
            try:
                page = get(f"{DIRECTORY}/{uid.lower()}.html", timeout)
                repo = pick_repo(re.findall(r'href="(https?://github\.com/kelu124/[^"]+)"', page, re.I)
                                 + re.findall(r'href="(https?://[^"]+)" class="button"', page))
            except Exception:
                repo = None
        found[uid] = {"uid": uid, "name": name, "date": date.group(1) if date else "",
                      "hardware": cell(row, "hardware"), "repo": repo}
    return found


def render(projects):
    lines = ["| Project | OSHWA UID | Certified | Hardware licence |", "|---|---|---|---|"]
    for p in sorted(projects.values(), key=lambda p: p["date"], reverse=True):
        name = f"**[{p['name']}]({p['repo']})**" if p["repo"] else f"**{p['name']}**"
        uid = f"[{p['uid']}]({DIRECTORY}/{p['uid'].lower()}.html)"
        lines.append(f"| {name} | {uid} | {p['date']} | {p['hardware']} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, don't write README")
    ap.add_argument("--hook", action="store_true", help="terse output for the SessionStart hook")
    args = ap.parse_args()
    timeout = 10 if args.hook else 30

    cache = json.loads(CACHE.read_text()).get("projects", {}) if CACHE.exists() else {}
    token = os.environ.get("OSHWA_TOKEN") or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")

    projects, source, errors = None, None, []
    if token:
        try:
            projects, source = from_api(token, timeout, cache), "API"
        except Exception as e:
            errors.append(f"API: {e}")
    if projects is None:
        try:
            projects, source = from_directory(timeout, cache), "public directory"
        except Exception as e:
            errors.append(f"directory: {e}")
    if not projects:
        if not args.hook:
            print("No OSHWA data available (" + "; ".join(errors or ["no matching projects"]) +
                  "). README table left as is.")
        return

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"updated": dt.date.today().isoformat(), "source": source,
                                 "projects": projects}, indent=2, ensure_ascii=False) + "\n")

    text = README.read_text()
    m = re.search(re.escape(START) + r"\n(.*?)\n?" + re.escape(END), text, re.S)
    if not m:
        if not args.hook:
            print(f"Markers {START} / {END} not in README.md; nothing written.")
        return
    table = render(projects)
    if m.group(1).strip() == table:
        if not args.hook:
            print(f"OSHWA table up to date ({len(projects)} projects, via {source}).")
        return

    old_uids = set(re.findall(r"\[([A-Z]{2}\d{6})\]", m.group(1)))
    added = sorted(set(projects) - old_uids)
    if args.check:
        print(f"OSHWA table out of date ({len(projects)} projects via {source}; new: {', '.join(added) or 'none'}).")
        return
    README.write_text(text[:m.start(1)] + table + "\n" + text[m.end(1):].lstrip("\n"))
    prefix = "[kelu124 profile — OSHWA] " if args.hook else ""
    print(f"{prefix}Updated the OSHWA-certified table in README.md ({len(projects)} projects via {source}"
          + (f"; new: {', '.join(projects[u]['name'] for u in added)}" if added else "")
          + "). Tell the user and offer to commit.")


if __name__ == "__main__":
    main()
