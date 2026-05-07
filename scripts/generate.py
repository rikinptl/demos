#!/usr/bin/env python3
"""
Slot-fill the static site template from leads.csv + skills packs.
No network / no AI — deterministic output for a single lead row.

Designed to run in GitHub Actions (see .github/workflows/pipeline.yml).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
TEMPLATE_PATH = REPO_ROOT / "templates" / "site.html"


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "business"


def stable_pick(seed: str, options: list) -> int:
    if not options:
        return 0
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % len(options)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_variant(manifest: dict, skill_key: str) -> tuple[str, dict]:
    """Return (variant_key, variant_data) using manifest fallback chain."""
    packs = manifest.get("packs", {})
    resolve = manifest.get("resolve", {})
    key = (skill_key or "").strip() or "generic"
    if key not in resolve:
        key = "generic"
    node = resolve[key]
    pack_name = node["pack"]
    variant = node["variant"]
    fallback: list[str] = list(node.get("fallback") or [])

    pack_file = SKILLS_DIR / packs[pack_name]
    pack = load_json(pack_file)
    variants = pack["variants"]

    chain = [variant] + fallback
    for vk in chain:
        if vk in variants:
            return vk, variants[vk]
    # Ultimate safety: first key in file
    first = next(iter(variants.values()))
    return chain[0], first


def read_leads(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader if any((v or "").strip() for v in r.values())]
        return reader.fieldnames or [], rows


def fmt_ctx(row: dict) -> dict:
    def g(k: str, default: str = "") -> str:
        v = row.get(k)
        return (v or "").strip() if v is not None else default

    return {
        "business_name": g("business_name", "Your business"),
        "category": g("category", "Local services"),
        "city": g("city", "your area"),
        "address": g("address", ""),
        "phone": g("phone"),
        "email": g("email"),
        "rating": g("rating"),
        "review_count": g("review_count"),
        "hours": g("hours"),
        "reviews_raw": g("reviews"),
        "years_in_business": g("years_in_business"),
        "services_notes": g("services_notes"),
    }


def phone_display(phone: str) -> tuple[str, str]:
    """(display text, tel: href value — '#' when unknown)."""
    p = (phone or "").strip()
    if not p:
        return "Call for a quote", "#"
    raw = re.sub(r"[^\d+]", "", p)
    if raw.startswith("1") and len(raw) == 11:
        raw = "+" + raw
    return p, raw or "#"


def parse_reviews(text: str) -> list[tuple[str, str]]:
    """Parse 'Name: body | Name2: body2' into [(first, body), ...]."""
    if not (text or "").strip():
        return []
    parts = re.split(r"\s*\|\s*", text)
    out: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if ":" in part:
            name, body = part.split(":", 1)
            first = name.strip().split()[0] if name.strip() else "Customer"
            out.append((first.strip(), body.strip()))
        elif part:
            out.append(("Customer", part))
    return out[:3]


def build_stats_html(ctx: dict, variant: dict) -> str:
    rating = ctx["rating"]
    rc = ctx["review_count"]
    years = ctx["years_in_business"]
    city = html.escape(ctx["city"])
    chunks: list[str] = []

    if rc:
        chunks.append(
            f"<div><strong>{html.escape(rc)}+</strong><span>Reviews</span></div>"
        )
    if rating:
        chunks.append(
            f"<div><strong>{html.escape(rating)}★</strong><span>Average</span></div>"
        )
    if years:
        chunks.append(
            f"<div><strong>{html.escape(years)}+</strong><span>Years in {city}</span></div>"
        )

    fb = variant.get("stats_fallback") or []
    i = 0
    while len(chunks) < 3 and i < len(fb):
        item = fb[i]
        num = html.escape(str(item.get("number", "")))
        lbl = html.escape(str(item.get("label", "")))
        chunks.append(f"<div><strong>{num}</strong><span>{lbl}</span></div>")
        i += 1
    while len(chunks) < 3:
        chunks.append("<div><strong>—</strong><span>Quality service</span></div>")
    return "\n".join(chunks[:3])


def merge_services(ctx: dict, variant: dict) -> list[dict]:
    base = list(variant.get("services") or [])
    notes = (ctx.get("services_notes") or "").strip()
    custom: list[dict] = []
    if notes:
        for piece in re.split(r"\s*,\s*", notes):
            t = piece.strip()
            if not t:
                continue
            custom.append(
                {
                    "icon": "▸",
                    "title": t,
                    "description": f"Requested often by homeowners in {ctx['city']}.",
                }
            )
    merged = custom + base
    return merged[:6]


def services_html(services: list[dict]) -> str:
    parts = []
    for s in services:
        ic = html.escape(s.get("icon", "•"))
        title = html.escape(s.get("title", ""))
        desc = html.escape(s.get("description", ""))
        parts.append(
            f'<div class="card"><div class="ic">{ic}</div><h3>{title}</h3><p>{desc}</p></div>'
        )
    return "\n".join(parts)


def features_html(ctx: dict, variant: dict) -> str:
    feats = variant.get("features") or []
    parts = []
    for f in feats:
        title = html.escape(f.get("title", ""))
        raw_desc = f.get("description", "")
        try:
            formatted = raw_desc.format(city=ctx["city"])
        except (KeyError, ValueError, IndexError):
            formatted = raw_desc
        desc = html.escape(formatted)
        parts.append(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>')
    return "\n".join(parts)


def reviews_html(ctx: dict, variant: dict) -> tuple[str, bool]:
    parsed = parse_reviews(ctx["reviews_raw"])
    voices = variant.get("review_voice") or [
        "Great experience.",
        "Highly recommend.",
        "Would hire again.",
    ]
    names = variant.get("synthetic_review_names") or ["Alex", "Jordan", "Sam"]
    parts: list[str] = []
    synthetic_used = False

    for i in range(3):
        if i < len(parsed):
            first, body = parsed[i]
            parts.append(
                '<div class="card quote-wrap"><p class="quote">'
                f"{html.escape(body)}</p>"
                f'<p class="who">— {html.escape(first)}., {html.escape(ctx["city"])}</p></div>'
            )
        else:
            synthetic_used = True
            body = voices[i % len(voices)]
            name = names[i % len(names)]
            parts.append(
                '<div class="card quote-wrap"><p class="quote">'
                f"{html.escape(body)}</p>"
                f'<p class="who">— {html.escape(name)}., {html.escape(ctx["city"])}</p></div>'
            )
    return "\n".join(parts), synthetic_used


def hours_html(hours: str) -> str:
    h = (hours or "").strip()
    if not h:
        return "<tr><td>Hours</td><td>Call for availability</td></tr>"
    if "\n" in h:
        chunks = [line.strip() for line in h.splitlines() if line.strip()]
    else:
        chunks = [h]
    if len(chunks) == 1:
        return f"<tr><td>Hours</td><td>{html.escape(chunks[0])}</td></tr>"
    rows = []
    for chunk in chunks:
        rows.append(f"<tr><td>Schedule</td><td>{html.escape(chunk)}</td></tr>")
    return "\n".join(rows)


def hero_lines(variant: dict, ctx: dict, seed: str) -> tuple[str, str]:
    pairs = variant.get("headline_pairs") or [["Quality service", "Near you."]]
    pair = pairs[stable_pick(seed, pairs)]
    line1 = pair[0].format(city=ctx["city"])
    line2 = pair[1].format(city=ctx["city"])
    return line1, line2


def hero_sub_text(ctx: dict, variant: dict) -> str:
    rc = (ctx["review_count"] or "").strip()
    rating = (ctx["rating"] or "").strip()
    if rc and rating:
        tpl = variant.get("hero_sub_with_reviews") or ""
        return tpl.format(
            review_count=rc, rating=rating, city=ctx["city"], business_name=ctx["business_name"]
        )
    tpl = variant.get("hero_sub_generic") or ""
    return tpl.format(city=ctx["city"], business_name=ctx["business_name"])


def generate(row: dict, manifest: dict) -> tuple[str, str, bool]:
    ctx = fmt_ctx(row)
    skill_key = (row.get("skill_key") or "").strip() or "generic"
    _vk, variant = resolve_variant(manifest, skill_key)

    seed = f"{ctx['business_name']}|{ctx['city']}|{skill_key}"
    line1, line2 = hero_lines(variant, ctx, seed)

    tagline = variant["tagline_template"].format(
        business_name=ctx["business_name"],
        category=ctx["category"],
        city=ctx["city"],
    )
    meta = variant["meta_desc_template"].format(
        business_name=ctx["business_name"],
        category=ctx["category"],
        city=ctx["city"],
    )

    phone_disp, phone_raw = phone_display(ctx["phone"])
    email_disp = ctx["email"] or "Contact us for details"

    rev_html, synthetic = reviews_html(ctx, variant)

    subs = {
        "NEON_COLOR": variant.get("neon_color", "#a78bfa"),
        "TAGLINE": html.escape(tagline),
        "META_DESC": html.escape(meta),
        "BUSINESS_NAME": html.escape(ctx["business_name"]),
        "CATEGORY": html.escape(ctx["category"]),
        "CITY": html.escape(ctx["city"]),
        "ADDRESS": html.escape(ctx["address"] or f"Serving {ctx['city']} and nearby areas."),
        "PHONE_DISPLAY": html.escape(phone_disp),
        "PHONE_RAW": html.escape(phone_raw),
        "EMAIL_DISPLAY": html.escape(email_disp),
        "HERO_LINE1": html.escape(line1),
        "HERO_LINE2": html.escape(line2),
        "HERO_SUB": html.escape(hero_sub_text(ctx, variant)),
        "STATS_HTML": build_stats_html(ctx, variant),
        "SERVICES_HTML": services_html(merge_services(ctx, variant)),
        "FEATURES_HTML": features_html(ctx, variant),
        "REVIEWS_HTML": rev_html,
        "HOURS_HTML": hours_html(ctx["hours"]),
        "YEAR": "2026",
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    out = template
    for k, v in subs.items():
        out = out.replace("{{" + k + "}}", v)

    slug = slugify(ctx["business_name"])
    return out, slug, synthetic


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate demo HTML from leads + skills.")
    ap.add_argument("--leads", type=Path, default=REPO_ROOT / "leads.csv")
    ap.add_argument("--row", type=int, default=-1, help="Row index (0-based). Default: last row.")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "output", help="Write output/<slug>/index.html")
    args = ap.parse_args()

    manifest = load_json(SKILLS_DIR / "manifest.json")
    _fields, rows = read_leads(args.leads)
    if not rows:
        raise SystemExit("No data rows in leads.csv")

    idx = args.row if args.row >= 0 else len(rows) - 1
    row = rows[idx]

    html_out, slug, synthetic = generate(row, manifest)
    out_dir = args.out_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html_out, encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"slug={slug}")
    print(f"synthetic_reviews={str(synthetic).lower()}")


if __name__ == "__main__":
    main()
