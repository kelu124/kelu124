#!/usr/bin/env python3
"""Keep the papers/publications list in README.md in sync.

Finds DOIs authored by Luc Jonveaux (ORCID 0000-0001-9003-4930) or published as kelu124,
and rewrites the list between <!-- PAPERS:START --> and <!-- PAPERS:END --> in README.md.

DOI discovery (all public, no token):
  - ORCID public API (the works on the ORCID record)
  - Crossref: works with the ORCID, or an author "Luc Jonveaux"
  - DataCite (Zenodo, arXiv, figshare...): creator with the ORCID or "Jonveaux, Luc",
    or records mentioning kelu124
  Other people named Jonveaux (Isabelle, Philippe...) are filtered out on the given name.
Metadata comes from doi.org content negotiation (CSL JSON), fetched once per DOI.

Cache and overrides live in .claude/history/papers.json:
  "exclude": DOIs to never list, "include": DOIs to always list (e.g. works about you
  but not authored by you) — both edited by hand; "works": cached metadata. A DOI once found
  stays listed even if a source is down later. To force a category, set "kind" (e.g.
  "software" or "text") plus "kind_manual": true on a work.
Zenodo concept/version DOIs (and other same-title duplicates) are collapsed into one entry.
If every source fails, or the markers are missing, README is left untouched.

Usage:
  python3 .claude/scripts/papers_sync.py          # sync and report
  python3 .claude/scripts/papers_sync.py --check  # report only, don't write
  python3 .claude/scripts/papers_sync.py --hook   # terse; silent when nothing changed
"""
import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CACHE = ROOT / ".claude" / "history" / "papers.json"
ORCID = "0000-0001-9003-4930"
START, END = "<!-- PAPERS:START -->", "<!-- PAPERS:END -->"
PAPER_TYPES = {"article", "article-journal", "journal-article", "paper-conference", "chapter",
               "book", "posted-content", "manuscript", "thesis", "preprint", "report", "speech"}


def get_json(url, timeout, accept="application/json", tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "kelu124-profile", "Accept": accept})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or i == tries - 1:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 2 * (i + 1))


def is_luc(given, family):
    return family.strip().lower() == "jonveaux" and given.strip().lower().startswith("l")


def from_orcid(timeout):
    d = get_json(f"https://pub.orcid.org/v3.0/{ORCID}/works", timeout)
    dois = set()
    for g in d.get("group", []):
        for e in g.get("external-ids", {}).get("external-id", []):
            if e["external-id-type"] == "doi":
                dois.add(e["external-id-value"].lower())
    return dois


def from_crossref(timeout):
    dois = set()
    d = get_json(f"https://api.crossref.org/works?filter=orcid:{ORCID}&rows=200&select=DOI", timeout)
    dois |= {w["DOI"].lower() for w in d["message"]["items"]}
    d = get_json("https://api.crossref.org/works?query.author=Luc+Jonveaux&rows=200&select=DOI,author", timeout)
    for w in d["message"]["items"]:
        if any(is_luc(a.get("given", ""), a.get("family", "")) for a in w.get("author", [])):
            dois.add(w["DOI"].lower())
    return dois


KINDS = {}  # doi -> DataCite resourceTypeGeneral, filled by from_datacite
NON_PAPER_KINDS = {"software", "dataset", "computationalnotebook", "collection", "image",
                   "audiovisual", "model", "workflow", "physicalobject", "service"}


def from_datacite(timeout):
    dois = set()

    def search(q):
        url = "https://api.datacite.org/dois?" + urllib.parse.urlencode({"query": q, "page[size]": 1000})
        data = get_json(url, timeout)["data"]
        for w in data:
            KINDS[w["attributes"]["doi"].lower()] = (w["attributes"]["types"].get("resourceTypeGeneral") or "").lower()
        return data

    for w in search(f'creators.nameIdentifiers.nameIdentifier:"https://orcid.org/{ORCID}"'):
        dois.add(w["attributes"]["doi"].lower())
    for w in search("creators.familyName:Jonveaux"):
        for c in w["attributes"].get("creators", []):
            given = c.get("givenName") or c.get("name", "").partition(",")[2]
            if is_luc(given, c.get("familyName") or c.get("name", "").partition(",")[0]):
                dois.add(w["attributes"]["doi"].lower())
    for w in search("kelu124"):
        if "kelu124" in json.dumps(w["attributes"]).lower():
            dois.add(w["attributes"]["doi"].lower())
    return dois


def fetch_meta(doi, timeout):
    c = get_json(f"https://doi.org/{urllib.parse.quote(doi)}", timeout,
                 accept="application/vnd.citationstyles.csl+json")
    title = c.get("title") or ""
    title = title[0] if isinstance(title, list) else title
    venue = c.get("container-title") or ""
    venue = venue[0] if isinstance(venue, list) else venue
    parts = (c.get("issued") or c.get("published") or {}).get("date-parts") or [[None]]
    return {
        "doi": doi,
        "title": re.sub(r"\s+", " ", title).strip(),
        "type": (c.get("type") or "").lower(),
        "venue": venue or c.get("publisher") or "",
        "year": parts[0][0],
        "authors": len(c.get("author", [])),
    }


def norm(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())


def pick(works):
    """One entry per title: prefer publisher DOIs over repositories, then Zenodo concept DOIs."""
    def rank(w):
        repo = any(k in w["doi"] for k in ("zenodo", "arxiv", "figshare"))
        num = re.search(r"(\d+)$", w["doi"])
        return (repo, int(num.group(1)) if num else 0)
    groups = {}
    for w in works:
        groups.setdefault(norm(w["title"]), []).append(w)
    return [sorted(g, key=rank)[0] for g in groups.values()]


def line(w):
    who = "" if w["authors"] <= 1 else f" · with {w['authors'] - 1} co-author{'s' if w['authors'] > 2 else ''}"
    venue = f" · *{w['venue']}*" if w["venue"] else ""
    return f"- {w['year'] or 'n.d.'} · **[{w['title']}](https://doi.org/{w['doi']})**{venue}{who}"


def is_paper(w):
    if w.get("kind"):
        return w["kind"] not in NON_PAPER_KINDS
    return w["type"] in PAPER_TYPES


def render(works):
    key = lambda w: (-(w["year"] or 0), w["title"].lower())
    papers = sorted((w for w in works if is_paper(w)), key=key)
    other = sorted((w for w in works if not is_paper(w)), key=key)
    out = []
    if papers:
        out += ["**Papers, preprints & reports**", ""] + [line(w) for w in papers]
    if other:
        out += ["", f"<details>\n<summary><b>Software & datasets with a DOI</b> ({len(other)})</summary>", ""]
        out += [line(w) for w in other] + ["", "</details>"]
    return "\n".join(out).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, don't write README")
    ap.add_argument("--hook", action="store_true", help="terse output for the SessionStart hook")
    args = ap.parse_args()
    timeout = 15 if args.hook else 30

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    exclude = {d.lower() for d in cache.get("exclude", [])}
    include = {d.lower() for d in cache.get("include", [])}
    known = cache.get("works", {})

    dois, errors = set(), []
    for name, fn in (("ORCID", from_orcid), ("Crossref", from_crossref), ("DataCite", from_datacite)):
        try:
            dois |= fn(timeout)
        except Exception as e:
            errors.append(f"{name}: {e}")
    if not dois:
        if not args.hook:
            print("No DOI source reachable (" + "; ".join(errors) + "). README left as is.")
        return

    dois |= include
    for doi in sorted(dois - exclude - set(known)):
        try:
            known[doi] = fetch_meta(doi, timeout)
        except Exception as e:
            errors.append(f"{doi}: {e}")
    for doi, kind in KINDS.items():
        if doi in known and not known[doi].get("kind_manual"):
            known[doi]["kind"] = kind
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"updated": dt.date.today().isoformat(), "exclude": sorted(exclude), "include": sorted(include),
                                 "works": dict(sorted(known.items()))}, indent=2, ensure_ascii=False) + "\n")

    # Every DOI ever found stays listed (a source being down must not drop entries);
    # remove one for good by adding it to "exclude".
    works = pick([w for d, w in known.items() if d not in exclude and w.get("title")])
    text = README.read_text()
    m = re.search(re.escape(START) + r"\n(.*?)\n?" + re.escape(END), text, re.S)
    if not m:
        if not args.hook:
            print(f"Markers {START} / {END} not in README.md; nothing written.")
        return
    block = render(works)
    note = f" ({'; '.join(errors)})" if errors and not args.hook else ""
    if m.group(1).strip() == block:
        if not args.hook:
            print(f"Papers list up to date ({len(works)} works){note}.")
        return
    old = set(re.findall(r"https://doi\.org/(\S+?)\)", m.group(1)))
    added = [w["title"] for w in works if w["doi"] not in old]
    if args.check:
        print(f"Papers list out of date ({len(works)} works; new: {len(added)}){note}.")
        return
    README.write_text(text[:m.start(1)] + block + "\n" + text[m.end(1):].lstrip("\n"))
    prefix = "[kelu124 profile — papers] " if args.hook else ""
    print(f"{prefix}Updated the papers list in README.md ({len(works)} works"
          + (f"; new: {'; '.join(added)}" if added and len(added) <= 5 else f"; {len(added)} new" if added else "")
          + f"){note}. Tell the user and offer to commit.")


if __name__ == "__main__":
    main()
