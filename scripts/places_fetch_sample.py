#!/usr/bin/env python3
"""Sample: Places API (New) Text Search — maps fields to lead-style data."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join(
    [
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


def main() -> None:
    load_env_file(ENV_PATH)
    api_key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if len(api_key) < 10:
        raise SystemExit(
            "GOOGLE_MAPS_API_KEY is missing or too short. Save demos/.env with your key after the =."
        )

    body = json.dumps(
        {
            "textQuery": "plumber near Dallas TX 75234",
            "maxResultCount": 5,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code}: {err}") from e

    places = payload.get("places") or []
    print(f"Found {len(places)} place(s).\n")

    for i, p in enumerate(places, 1):
        website = (p.get("websiteUri") or "").strip()
        print(f"--- {i}. {name_text(p.get('displayName'))} ---")
        print(f"  place_id: {p.get('id', '')}")
        print(f"  address:  {p.get('formattedAddress', '')}")
        print(f"  phone:    {p.get('nationalPhoneNumber', '')}")
        print(f"  rating:   {p.get('rating', '')} ({p.get('userRatingCount', '')} reviews)")
        print(f"  website:  {website or '(none on profile — candidate for your pipeline)'}")
        types = p.get("types") or []
        if types:
            print(f"  types:    {', '.join(types[:5])}{'…' if len(types) > 5 else ''}")
        hours = p.get("regularOpeningHours")
        if hours:
            desc = json.dumps(hours)
            print(f"  hours:    {desc[:240]}{'…' if len(desc) > 240 else ''}")
        print()


if __name__ == "__main__":
    main()
