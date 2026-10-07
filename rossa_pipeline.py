#!/usr/bin/env python3
"""ROSSA entry-item pipeline for Team 51 (Dr. Shin's 9-30 To-Do).

Steps, matching the slide "Ingesting PDF and producing entry items for ROSSA":

  ingest   Step 1   PDF -> clean article text
  build    Step 2   article text + ROSSA schema -> one prompt JSON per section
                    (2a study information, 2b investigators, 2c animal experimentation)
  submit   Step 3   send each prompt JSON to an LLM, save the JSON it returns
  process  Step 3   validate the replies, check every quoted passage really appears
                    in the paper, write the entry JSON and a human review sheet

Usage:
  python rossa_pipeline.py ingest input/doyard_2016.pdf
  python rossa_pipeline.py build doyard_2016
  python rossa_pipeline.py submit doyard_2016                       # manual: paste into Claude
  python rossa_pipeline.py submit doyard_2016 --backend anthropic   # needs ANTHROPIC_API_KEY
  python rossa_pipeline.py process doyard_2016
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SCHEMA_PATH = HERE / "rossa_schema.json"

SECTIONS = {
    "study_information": "2a",
    "investigators": "2b",
    "animal_experimentation": "2c",
}
CONFIDENCE = ("high", "medium", "low", "not_found")
DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = (
    "You fill in metadata entry fields for ROSSA (the Rodent Open Science Skeletal Archive) "
    "from the text of one scientific article. Use only what the article text says; never use "
    "outside knowledge to fill a gap. Reply with one JSON object and nothing else."
)

GENERAL_RULES = [
    "Use only the text in article_text. If the article does not state a value, set value to null, "
    "evidence to null and confidence to \"not_found\". Do not guess.",
    "For every non-null value give evidence: an exact, contiguous quote copied from the article "
    "(at most 250 characters). If one value combines several places, give a list of quotes. "
    "Never paraphrase inside evidence.",
    "confidence: \"high\" = stated directly; \"medium\" = needs a small inference such as matching "
    "a superscript number to an affiliation; \"low\" = weakly supported or ambiguous.",
    "Booleans: use true only when the article shows the study uses that variable. For false, "
    "evidence may be null.",
    "For list fields return one object per item, or [] if the article has none.",
    "Put anything a human reviewer should double-check (suspected typos, unclear wording, "
    "judgement calls) in reviewer_flags as short sentences.",
    "Return output_template filled in, plus reviewer_flags. No prose and no markdown fences.",
]


# ---------------------------------------------------------------- schema helpers
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def fields(node: dict) -> dict:
    """Schema children of a group, skipping the _title/_rules bookkeeping keys."""
    return {k: v for k, v in node.items() if not k.startswith("_")}


def is_group(node: dict) -> bool:
    return "type" not in node


def template_for(node: dict):
    """Blank output template: every leaf becomes {value, evidence, confidence}."""
    if is_group(node):
        return {k: template_for(v) for k, v in fields(node).items()}
    if node["type"] == "list":
        return [template_for(node["item"])]
    return {"value": None, "evidence": None, "confidence": "not_found"}


def field_definitions(node: dict, path: str = "") -> dict:
    """Flat {dotted.path: description} map so the model knows what each field means."""
    defs = {}
    for key, spec in fields(node).items():
        p = f"{path}.{key}" if path else key
        if is_group(spec):
            defs.update(field_definitions(spec, p))
        elif spec["type"] == "list":
            defs.update(field_definitions(spec["item"], p + "[]"))
        else:
            d = {"type": spec["type"], "description": spec["description"]}
            if "enum" in spec:
                d["allowed_values"] = spec["enum"]
            defs[p] = d
    return defs


# ---------------------------------------------------------------- step 1: ingest
def normalize_chars(s: str) -> str:
    s = s.replace("−", "-").replace(" ", " ").replace("­", "")
    return unicodedata.normalize("NFKC", s)


def drop_running_lines(pages: list[str]) -> tuple[list[str], int]:
    """Remove page headers/footers: short lines that repeat on many pages (digits ignored)."""
    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip())

    counts = Counter()
    for p in pages:
        counts.update({key(l) for l in p.splitlines() if l.strip()})
    cutoff = max(3, int(0.4 * len(pages)))
    noisy = {k for k, n in counts.items() if n >= cutoff and len(k) < 120}
    removed = 0
    cleaned = []
    for p in pages:
        keep = []
        for l in p.splitlines():
            if key(l) in noisy:
                removed += 1
            else:
                keep.append(l)
        cleaned.append("\n".join(keep))
    return cleaned, removed


def cut_references(text: str) -> str:
    hits = list(re.finditer(r"^\s*References\s*$", text, flags=re.M | re.I))
    if hits and hits[-1].start() > 0.5 * len(text):
        return text[: hits[-1].start()]
    return text


def cmd_ingest(args) -> None:
    from pypdf import PdfReader

    pdf = Path(args.pdf)
    paper_id = args.id or pdf.stem
    pages = [normalize_chars(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    pages, removed = drop_running_lines(pages)
    text = cut_references(re.sub(r"\n{3,}", "\n\n", "\n".join(pages))).strip()
    if len(text) < 2000:
        sys.exit("Very little text came out. This PDF may be scanned images; it needs OCR first.")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{paper_id}.txt").write_text(text, encoding="utf-8")
    print(f"{pdf.name}: {len(pages)} pages -> {len(text):,} characters "
          f"({removed} header/footer lines removed, reference list cut)")
    print(f"wrote output/{paper_id}.txt")


# ---------------------------------------------------------------- step 2: build
def prompt_path(pid: str, section: str) -> Path:
    return OUT / f"{pid}.{section}.prompt.json"


def response_path(pid: str, section: str, tag: str = "") -> Path:
    """Reply file. tag="" is the canonical name (used by the manual worked example);
    an API backend tags its replies (e.g. '.gemini') so runs don't overwrite each other."""
    dot = f".{tag}" if tag else ""
    return OUT / f"{pid}.{section}{dot}.response.json"


# which reply files a backend writes, and which `process --from` reads
BACKEND_TAG = {"manual": "", "anthropic": "claude", "gemini": "gemini"}


def cmd_build(args) -> None:
    schema = load_schema()
    text = (OUT / f"{args.id}.txt").read_text(encoding="utf-8")
    for section, step in SECTIONS.items():
        node = schema["sections"][section]
        prompt = {
            "meta": {
                "paper_id": args.id,
                "section": section,
                "slide_step": step,
                "schema_version": schema["_meta"]["version"],
                "schema_status": schema["_meta"]["status"],
                "created": date.today().isoformat(),
            },
            "system_prompt": SYSTEM_PROMPT,
            "request": {
                "task": f"Fill in the ROSSA entry fields for: {node['_title']}.",
                "rules": GENERAL_RULES + node.get("_rules", []),
                "field_definitions": field_definitions(node),
                "output_template": {**template_for(node), "reviewer_flags": []},
                "article_text": text,
            },
        }
        prompt_path(args.id, section).write_text(
            json.dumps(prompt, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {prompt_path(args.id, section).relative_to(HERE)}  (step {step})")


# ---------------------------------------------------------------- step 3: submit
def parse_json_loose(raw: str) -> dict:
    """Accept a model reply even if it wrapped the JSON in a code fence."""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object found in the reply")
    return json.loads(s[a:b + 1])


def call_claude(prompt: dict, model: str, fallback: bool) -> tuple[str, dict]:
    try:
        import anthropic
    except ImportError:
        sys.exit("Install the SDK first:  pip install anthropic")

    kwargs = dict(
        model=model,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=prompt["system_prompt"],
        messages=[{"role": "user",
                   "content": json.dumps(prompt["request"], ensure_ascii=False)}],
    )
    try:
        client = anthropic.Anthropic()  # ANTHROPIC_API_KEY or an `ant auth login` profile
        if fallback:
            # Server-side refusal fallback. The installed SDK predates the typed `fallbacks`
            # argument, so it goes in extra_body. Life-science text can trip safety classifiers.
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"}, **kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except (anthropic.AuthenticationError, TypeError):
        sys.exit("No Anthropic credentials found. Set ANTHROPIC_API_KEY in your shell "
                 "(do not paste a key into any file) or run `ant auth login`.")
    except anthropic.NotFoundError:
        sys.exit(f"Model '{model}' was not found. Try --model with another model ID.")
    except anthropic.BadRequestError as e:
        sys.exit(f"Bad request: {e.message}\nIf it mentions fallbacks, retry with --no-fallback.")
    except anthropic.RateLimitError:
        sys.exit("Rate limited. Wait a minute and run submit again.")
    except anthropic.APIConnectionError:
        sys.exit("Network error. Check your internet connection.")
    except anthropic.APIStatusError as e:
        sys.exit(f"API error {e.status_code}: {e.message}")

    if resp.stop_reason == "refusal":
        sys.exit("Claude declined this request (stop_reason=refusal). Nothing saved.")
    if resp.stop_reason == "max_tokens":
        print("warning: reply hit max_tokens and may be cut off")
    text = "".join(b.text for b in resp.content if b.type == "text")
    meta = {"backend": "anthropic", "model": resp.model, "stop_reason": resp.stop_reason,
            "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return text, meta


def call_gemini(prompt: dict, model: str) -> tuple[str, dict]:
    """Google Gemini via the free AI Studio tier. Key from GEMINI_API_KEY or GOOGLE_API_KEY."""
    import os
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("Install the Gemini SDK first:  pip install google-genai")

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("No Gemini key. Make a free one at https://aistudio.google.com/apikey , then in "
                 "your shell:  export GEMINI_API_KEY=...  (never put the key in a file).")

    client = genai.Client(api_key=key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=json.dumps(prompt["request"], ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=prompt["system_prompt"],
                response_mime_type="application/json",  # force a JSON-only reply
                temperature=0,
            ),
        )
    except Exception as e:  # the SDK raises its own error types; show the message plainly
        sys.exit(f"Gemini request failed: {e}")

    text = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    meta = {"backend": "gemini", "model": model,
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None)}
    return text, meta


# default model per backend
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def cmd_submit(args) -> None:
    tag = BACKEND_TAG[args.backend]
    for section, step in SECTIONS.items():
        pp, rp = prompt_path(args.id, section), response_path(args.id, section, tag)
        prompt = json.loads(pp.read_text(encoding="utf-8"))
        if args.backend == "manual":
            paste = OUT / f"{args.id}.{section}.paste.txt"
            paste.write_text(prompt["system_prompt"] + "\n\n"
                             + json.dumps(prompt["request"], indent=2, ensure_ascii=False),
                             encoding="utf-8")
            state = "reply found" if rp.exists() else "waiting for reply"
            print(f"step {step}: paste {paste.relative_to(HERE)} into an LLM chat "
                  f"(e.g. claude.ai or gemini.google.com), then save its JSON reply as "
                  f"{rp.relative_to(HERE)}  [{state}]")
            continue
        if args.backend == "anthropic":
            model = args.model or DEFAULT_MODEL
            text, meta = call_claude(prompt, model, not args.no_fallback)
        else:  # gemini
            model = args.model or DEFAULT_GEMINI_MODEL
            text, meta = call_gemini(prompt, model)
        try:
            obj = parse_json_loose(text)
            obj["_meta"] = meta
            rp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        except (ValueError, json.JSONDecodeError):
            rp.write_text(text, encoding="utf-8")
            print(f"warning: step {step} reply was not valid JSON; saved raw text")
        print(f"step {step}: saved {rp.relative_to(HERE)} ({meta['output_tokens']} output tokens)")


# ---------------------------------------------------------------- step 3: process
def squash(s: str) -> str:
    """Letters and digits only, case-folded, accents stripped. Lets a quote match across
    line breaks, hyphenation, curly quotes, superscripts and differing accent encodings
    (PDF extraction routinely mangles diacritics, e.g. Loreal vs Loreal)."""
    decomposed = unicodedata.normalize("NFKD", s)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", "", no_marks.casefold())


def type_ok(spec: dict, v) -> bool:
    t = spec["type"]
    if t == "string":
        return isinstance(v, str)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "enum":
        return v in spec["enum"]
    return False


class Audit:
    def __init__(self, article: str):
        self.hay = squash(article)
        self.rows: list[dict] = []
        self.problems: list[str] = []


def check(spec: dict, resp, path: str, audit: Audit):
    """Validate a reply against the schema; return plain values only."""
    if is_group(spec):
        if not isinstance(resp, dict):
            audit.problems.append(f"{path}: expected an object")
            return {}
        for extra in sorted(set(resp) - set(fields(spec))):
            audit.problems.append(f"{path}.{extra}: unexpected field (ignored)")
        out = {}
        for key, sub in fields(spec).items():
            if key not in resp:
                audit.problems.append(f"{path}.{key}: missing from reply")
                out[key] = None
            else:
                out[key] = check(sub, resp[key], f"{path}.{key}", audit)
        return out
    if spec["type"] == "list":
        if not isinstance(resp, list):
            audit.problems.append(f"{path}: expected a list")
            return []
        return [check(spec["item"], item, f"{path}[{i}]", audit) for i, item in enumerate(resp)]
    return check_leaf(spec, resp, path, audit)


def check_leaf(spec: dict, resp, path: str, audit: Audit):
    if not (isinstance(resp, dict) and {"value", "evidence", "confidence"} <= set(resp)):
        audit.problems.append(f"{path}: expected {{value, evidence, confidence}}")
        return None
    value, evidence, conf = resp["value"], resp["evidence"], resp["confidence"]
    notes = []
    if conf not in CONFIDENCE:
        notes.append(f"unknown confidence '{conf}'")
        conf = "low"
    bad_type = value is not None and not type_ok(spec, value)
    if bad_type:
        notes.append(f"{value!r} is not a valid {spec['type']}"
                     + (f" (allowed: {', '.join(spec['enum'])})" if "enum" in spec else ""))
    needs_evidence = value is not None and not (spec["type"] == "boolean" and value is False)
    verified = None
    if needs_evidence:
        quotes = [q for q in (evidence if isinstance(evidence, list) else [evidence])
                  if isinstance(q, str) and q.strip()]
        if not quotes:
            notes.append("no evidence quote")
            verified = False
        else:
            bad = [q for q in quotes if len(squash(q)) < 12 or squash(q) not in audit.hay]
            if bad:
                notes.append("quote not found in the paper: \"" + bad[0][:70] + "\"")
            verified = not bad
    if verified is False or bad_type:
        conf = "low" if conf != "not_found" else conf
    audit.rows.append({"path": path, "value": value, "confidence": conf,
                       "verified": verified, "notes": notes, "evidence": evidence})
    if notes:
        audit.problems.append(f"{path}: " + "; ".join(notes))
    return value


def show(v, width: int = 80) -> str:
    if v is None:
        s = "-"
    elif isinstance(v, str):
        s = v
    else:
        s = json.dumps(v, ensure_ascii=False)
    return (s[: width - 1] + "…") if len(s) > width else s


def cmd_process(args) -> None:
    schema = load_schema()
    tag = BACKEND_TAG[args.source]
    out_tag = f".{tag}" if tag else ""
    article = (OUT / f"{args.id}.txt").read_text(encoding="utf-8")
    audit = Audit(article)
    entry = {"paper_id": args.id, "generated": date.today().isoformat(),
             "source": args.source,
             "status": "DRAFT - human review required before anything is submitted to ROSSA",
             "schema": f"{schema['_meta']['version']} (provisional)"}
    flags, producers, section_rows = {}, {}, {}
    start = 0

    for section, step in SECTIONS.items():
        rp = response_path(args.id, section, tag)
        if not rp.exists():
            sys.exit(f"Missing reply for step {step}: {rp.relative_to(HERE)}\n"
                     f"Run `submit` for the '{args.source}' backend first and save the JSON there.")
        try:
            resp = parse_json_loose(rp.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as e:
            sys.exit(f"{rp.name} is not valid JSON ({e}).")
        producers[section] = resp.pop("_meta", "unspecified")
        flags[section] = resp.pop("reviewer_flags", [])
        entry[section] = check(schema["sections"][section], resp, section, audit)
        section_rows[section] = audit.rows[start:]
        start = len(audit.rows)

    md = [f"# ROSSA entry review: {args.id}  (source: {args.source})", "",
          "Draft produced by the pipeline. Nothing here is submitted anywhere; a person checks every row.", ""]
    for section in SECTIONS:
        md += [f"## {schema['sections'][section]['_title']}", "",
               "| Field | Suggested value | Confidence | Quote check |", "|---|---|---|---|"]
        for r in section_rows[section]:
            check_txt = {True: "verified in paper", False: "NOT VERIFIED", None: "n/a"}[r["verified"]]
            short = r["path"].split(".", 1)[1]
            md.append(f"| {short} | {show(r['value']).replace('|', '/')} | {r['confidence']} | {check_txt} |")
        md.append("")
        if flags[section]:
            md += ["Reviewer flags from the model:", ""] + [f"- {f}" for f in flags[section]] + [""]
        md += [f"Produced by: {json.dumps(producers[section], ensure_ascii=False)}", ""]

    filled = [r for r in audit.rows if r["value"] is not None]
    verified = [r for r in filled if r["verified"]]
    unverified = [r for r in audit.rows if r["verified"] is False]
    md += ["## Summary", "",
           f"- {len(audit.rows)} fields checked, {len(filled)} filled, "
           f"{len(audit.rows) - len(filled)} left empty (not found).",
           f"- {len(verified)} values have a quote that was found verbatim in the paper.",
           f"- {len(unverified)} values have a missing or unfindable quote (confidence forced to low)."]
    if audit.problems:
        md += ["", "Pipeline problems:", ""] + [f"- {p}" for p in audit.problems]

    entry.update({"reviewer_flags": flags, "produced_by": producers,
                  "audit": [{k: r[k] for k in ("path", "confidence", "verified", "notes")}
                            for r in audit.rows],
                  "pipeline_problems": audit.problems})
    (OUT / f"{args.id}{out_tag}.entry.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / f"{args.id}{out_tag}.review.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[{args.source}] {len(audit.rows)} fields checked | {len(filled)} filled | "
          f"{len(verified)} quotes verified | {len(unverified)} unverified | "
          f"{len(audit.problems)} problems")
    print(f"wrote output/{args.id}{out_tag}.entry.json and output/{args.id}{out_tag}.review.md")


# ---------------------------------------------------------------- cli
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="PDF -> clean text")
    p.add_argument("pdf")
    p.add_argument("--id", help="paper id (default: the PDF file name)")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("build", help="text + schema -> prompt JSON files")
    p.add_argument("id")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("submit", help="send prompts to an LLM")
    p.add_argument("id")
    p.add_argument("--backend", choices=["manual", "anthropic", "gemini"], default="manual",
                   help="manual = write paste files; anthropic = Claude API; gemini = Gemini API")
    p.add_argument("--model", default=None,
                   help="override the model (default: claude-opus-5-5 or gemini-2.5-flash)")
    p.add_argument("--no-fallback", action="store_true",
                   help="anthropic only: skip the server-side refusal fallback")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("process", help="validate replies, verify quotes, write entry + review")
    p.add_argument("id")
    p.add_argument("--source", choices=["manual", "anthropic", "gemini"], default="manual",
                   help="which backend's replies to grade (default: manual)")
    p.set_defaults(fn=cmd_process)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
