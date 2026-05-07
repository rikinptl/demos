#!/usr/bin/env python3
"""
Print a cold-email draft to stdout (no sending). Wire Resend in a later week.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leads", type=Path, default=REPO_ROOT / "leads.csv")
    ap.add_argument("--row", type=int, default=-1)
    ap.add_argument("--url", type=str, default="", help="Demo URL to embed")
    args = ap.parse_args()

    with args.leads.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    idx = args.row if args.row >= 0 else len(rows) - 1
    r = rows[idx]
    name = (r.get("business_name") or "").strip()
    city = (r.get("city") or "").strip()
    cat = (r.get("category") or "").strip()
    rating = (r.get("rating") or "").strip()
    url = args.url or "(deploy demo URL here)"

    subject = f"I built a free website demo for {name}"
    opening = f"I noticed {name} in {city}"
    if rating:
        opening += f" — strong {rating}★ visibility locally"
    opening += f" and put together a quick one-page preview for a {cat} shop like yours."

    body = f"""Subject: {subject}

{opening}

No strings attached — it's a real preview you can click through:
{url}

If you like the direction, I can connect it to your domain, booking, and SEO. Reply or call me and we'll line up a time.

— Your name
Your phone
"""
    print(body)


if __name__ == "__main__":
    main()
