# ROSSA metadata pipeline

Senior design, Team 51. Takes a skeletal-biology paper (PDF) and drafts the ROSSA
submission fields for three sections (study info, investigators, animal experimentation).
For each value the LLM has to give the exact quote it came from, and the script checks
that quote is actually in the paper before anything goes to a human to review.

## Setup

```
pip install anthropic pypdf
```

## Run

```
python rossa_pipeline.py ingest input/doyard_2016.pdf
python rossa_pipeline.py build doyard_2016
python rossa_pipeline.py submit doyard_2016
python rossa_pipeline.py process doyard_2016
```

Output ends up in `output/` — `doyard_2016.entry.json` is the result, `doyard_2016.review.md`
is a readable version.

## Notes

- `submit` has two modes: paste each `output/*.paste.txt` into an LLM by hand, or use
  `--backend anthropic` or `--backend gemini` to call the API (key goes in an env var, not a file).
- `rossa_schema.json` holds the ROSSA fields and dropdown values, taken from the live form.
- Doyard 2016 is left in as a worked example.
