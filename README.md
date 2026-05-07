# Demos pipeline

Manual lead → slot-filled static site → (later) GitHub Pages + email.

## Layout

- `leads.csv` — one row per business; `skill_key` maps to `skills/manifest.json`.
- `skills/` — JSON packs (`home_services.json`) + manifest with fallback chain.
- `templates/site.html` — fixed layout; `{{PLACEHOLDERS}}` only.
- `scripts/generate.py` — deterministic merge (no AI yet).
- `scripts/email_draft.py` — prints a cold email stub (no API).
- `.github/workflows/pipeline.yml` — runs generator on `leads.csv` / skills / template changes; uploads `output/` as an artifact.

## Local run

```bash
python3 scripts/generate.py
# optional: python3 scripts/generate.py --row 0
open output/<slug>/index.html
```

## Next steps

- Point GitHub Pages at `gh-pages` and add a job to commit `output/<slug>/index.html` under `/demos/<slug>/`.
- Single Groq call for tagline / hero sub / email opener / synthetic reviews.
- Resend (or Brevo) send step + append `data/tracking.csv`.
