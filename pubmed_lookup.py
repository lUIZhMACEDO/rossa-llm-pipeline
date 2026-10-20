"""Find a paper's PubMed ID, which is usually not printed in the PDF.

Uses NCBI E-utilities (free, no key needed for a few requests per second):
  1. search PubMed by DOI
  2. if nothing comes back, search by exact title
  3. fetch the record's summary and confirm its title matches the paper before accepting it

usage:  python pubmed_lookup.py doyard_2016            (reads output/<id>.entry.json, or any tagged entry)
        python pubmed_lookup.py --doi 10.7554/eLife.49631 --title "Stimulation of Piezo1 ..."
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
OUT = Path(__file__).resolve().parent / "output"


def get(endpoint, **params):
    params.update(retmode="json", tool="rossa_pipeline")
    url = EUTILS + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read())
    time.sleep(0.4)   # stay under NCBI's 3 requests/second limit
    return data


def search(term):
    return get("esearch.fcgi", db="pubmed", term=term)["esearchresult"].get("idlist", [])


def letters(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def lookup(doi=None, title=None):
    """Return {pubmed_id, matched_by, pubmed_title, title_match} or {pubmed_id: None, ...}."""
    tried = []
    for how, term in (("doi", f"{doi}[doi]" if doi else None),
                      ("title", f"\"{title}\"[ti]" if title else None)):
        if not term:
            continue
        tried.append(how)
        ids = search(term)
        if len(ids) != 1:
            continue
        rec = get("esummary.fcgi", db="pubmed", id=ids[0])["result"][ids[0]]
        score = SequenceMatcher(None, letters(rec.get("title")), letters(title)).ratio() if title else None
        if score is not None and score < 0.85:
            continue   # a different paper; do not accept it
        return {"pubmed_id": ids[0], "matched_by": how, "pubmed_title": rec.get("title"),
                "journal": rec.get("fulljournalname"), "pub_date": rec.get("pubdate"),
                "title_match": None if score is None else round(score, 2)}
    return {"pubmed_id": None, "matched_by": None, "tried": tried}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", nargs="?")
    ap.add_argument("--doi")
    ap.add_argument("--title")
    ap.add_argument("--tag", default="", help="which entry to read, e.g. huggingface")
    a = ap.parse_args()
    doi, title = a.doi, a.title
    if a.id:
        name = f"{a.id}.{a.tag}.entry.json" if a.tag else f"{a.id}.entry.json"
        si = json.loads((OUT / name).read_text(encoding="utf-8"))["study_information"]
        doi, title = doi or si.get("doi"), title or si.get("title")
    print(json.dumps(lookup(doi, title), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
