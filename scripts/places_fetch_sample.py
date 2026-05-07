#!/usr/bin/env python3
"""
Places API (New) Text Search — places with no websiteUri, then optional Place Details
for reviews + extra context (editorial summary, primary type, Maps link).

Billing: Text Search + one Place Details call per printed lead. Fields like ``reviews``
and ``editorialSummary`` are priced as Enterprise + Atmosphere on Place Details — check
current Maps Platform pricing before scaling.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

PLACE_FIELDS = [
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.regularOpeningHours",
    "places.types",
]
SEARCH_FIELD_MASK = ",".join(PLACE_FIELDS + ["nextPageToken"])

# Place Details (GET) — enrichment for the site generator / leads.csv
DETAILS_FIELD_MASK = ",".join(
    [
        "reviews",
        "editorialSummary",
        "primaryType",
        "primaryTypeDisplayName",
        "googleMapsUri",
    ]
)


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val


def name_text(display_name: object) -> str:
    if display_name is None:
        return ""
    if isinstance(display_name, dict):
        return str(display_name.get("text") or "")
    return str(display_name)


def localized_plain(obj: object) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return str(obj.get("text") or "").strip()
    return str(obj).strip()


def has_website(place: dict[str, Any]) -> bool:
    return bool((place.get("websiteUri") or "").strip())


def fetch_search_page(api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        SEARCH_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code}: {err}") from e


def fetch_place_details(api_key: str, place_id: str) -> dict[str, Any]:
    """GET places/{place_id} — place_id is the short id (e.g. ChIJ…)."""
    url = f"https://places.googleapis.com/v1/places/{quote(place_id, safe='')}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": DETAILS_FIELD_MASK,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Place Details HTTP {e.code} for {place_id}: {err}") from e


def author_first(att: object) -> str:
    if not isinstance(att, dict):
        return "Customer"
    name = (att.get("displayName") or "").strip()
    return name.split()[0] if name else "Customer"


def review_body(r: dict[str, Any]) -> str:
    t = r.get("text")
    if isinstance(t, dict):
        return (t.get("text") or "").strip()
    if isinstance(t, str):
        return t.strip()
    return ""


def format_reviews_for_csv(reviews: list[dict[str, Any]], max_reviews: int) -> str:
    """Pipe-separated segments for leads.csv ``reviews`` column: Name: text | …"""
    parts: list[str] = []
    for r in reviews[:max_reviews]:
        body = review_body(r)
        if not body:
            continue
        first = author_first(r.get("authorAttribution"))
        parts.append(f"{first}: {body}")
    return " | ".join(parts)


def print_place(
    i: int,
    p: dict[str, Any],
    details: dict[str, Any] | None,
    *,
    max_review_snippets: int,
) -> None:
    print(f"--- {i}. {name_text(p.get('displayName'))} ---")
    print(f"  place_id: {p.get('id', '')}")
    print(f"  address:  {p.get('formattedAddress', '')}")
    print(f"  phone:    {p.get('nationalPhoneNumber', '')}")
    print(f"  rating:   {p.get('rating', '')} ({p.get('userRatingCount', '')} reviews)")
    print("  website:  (none on Google profile)")
    types = p.get("types") or []
    if types:
        print(f"  types:    {', '.join(types[:5])}{'…' if len(types) > 5 else ''}")
    hours = p.get("regularOpeningHours")
    if hours:
        desc = json.dumps(hours)
        print(f"  hours:    {desc[:240]}{'…' if len(desc) > 240 else ''}")

    if details:
        ptype = localized_plain(details.get("primaryTypeDisplayName"))
        if ptype:
            print(f"  primary_type: {ptype}")
        summ = localized_plain(details.get("editorialSummary"))
        if summ:
            print(f"  google_summary: {summ}")
        gmaps = (details.get("googleMapsUri") or "").strip()
        if gmaps:
            print(f"  maps_link: {gmaps}")

        revs = details.get("reviews") or []
        # API returns up to 5, relevance-sorted
        text_revs = [r for r in revs if isinstance(r, dict) and review_body(r)]
        if text_revs:
            print(f"  reviews ({len(text_revs)} with text, show top {max_review_snippets}):")
            for j, r in enumerate(text_revs[:max_review_snippets], 1):
                stars = r.get("rating", "")
                who = author_first(r.get("authorAttribution"))
                when = (r.get("relativePublishTimeDescription") or "").strip()
                body = review_body(r)
                tail = f" ({when})" if when else ""
                print(f"    {j}. ★{stars} {who}: {body[:320]}{'…' if len(body) > 320 else ''}{tail}")
            csv_blob = format_reviews_for_csv(text_revs, max_review_snippets)
            if csv_blob:
                print(f"  reviews_for_leads_csv: {csv_blob}")
        else:
            print("  reviews: (none with text in API response — use rating or synthetic copy)")

    print()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="List Places with no websiteUri; optionally fetch reviews + summary."
    )
    ap.add_argument(
        "--query",
        default="plumber near Dallas TX 75234",
        help="Text search query",
    )
    ap.add_argument(
        "--want",
        type=int,
        default=10,
        help="Stop after this many no-website places (default 10)",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=8,
        help="Max search pages (20 results/page max)",
    )
    ap.add_argument(
        "--no-details",
        action="store_true",
        help="Skip Place Details (no reviews/editorial summary; cheaper)",
    )
    ap.add_argument(
        "--details-delay",
        type=float,
        default=0.15,
        help="Seconds between Place Details calls (default 0.15)",
    )
    ap.add_argument(
        "--max-review-snippets",
        type=int,
        default=5,
        help="Max reviews to print / pass through for leads (API returns at most 5)",
    )
    args = ap.parse_args()

    load_env_file(ENV_PATH)
    api_key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if len(api_key) < 10:
        raise SystemExit(
            "GOOGLE_MAPS_API_KEY is missing or too short. Save demos/.env with your key after the =."
        )

    base: dict[str, Any] = {
        "textQuery": args.query,
        "pageSize": 20,
    }

    no_site: list[dict[str, Any]] = []
    scanned = 0
    page_token: str | None = None
    pages = 0

    while len(no_site) < args.want and pages < args.max_pages:
        body = {**base}
        if page_token:
            body["pageToken"] = page_token

        payload = fetch_search_page(api_key, body)
        places = payload.get("places") or []
        scanned += len(places)

        for p in places:
            if not has_website(p):
                no_site.append(p)
                if len(no_site) >= args.want:
                    break

        page_token = (payload.get("nextPageToken") or "").strip() or None
        pages += 1
        if not page_token:
            break

    print(
        f"Scanned {scanned} place(s) in {pages} page(s); "
        f"{len(no_site)} with no website on profile.\n"
    )
    if not args.no_details:
        print(
            "Fetching Place Details per lead (reviews + editorialSummary + primary type)…\n"
        )

    if not no_site:
        print(
            "No matches. Try a broader query, different area, or another category — "
            "many listings include a website."
        )
        return

    for i, p in enumerate(no_site, 1):
        details: dict[str, Any] | None = None
        if not args.no_details:
            pid = (p.get("id") or "").strip()
            if pid:
                details = fetch_place_details(api_key, pid)
                if args.details_delay > 0:
                    time.sleep(args.details_delay)
        print_place(i, p, details, max_review_snippets=args.max_review_snippets)


if __name__ == "__main__":
    main()
