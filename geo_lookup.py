"""
geo_lookup.py
-------------
Fully OFFLINE geocoder. No third-party API, no rate limits, no internet
needed at runtime, no Terms-of-Service restrictions on storing coordinates.

Data source: the `geonamescache` PyPI package, which bundles GeoNames data
(CC-BY licensed) for ~32,000 cities worldwide with population >= 15,000.
This includes towns like Barbil, Odisha.

  pip install geonamescache

Usage:
    from geo_lookup import city_to_latlon
    coords = city_to_latlon("Barbil, Odisha")   # -> (22.10194, 85.37752)
    coords = city_to_latlon("Mumbai, India")    # -> (lat, lon)
    coords = city_to_latlon("London, UK")       # -> (lat, lon)
    # returns None if nothing matches

If you later need EVERY village (population < 15,000), see the note at the
bottom of this file for swapping in the full GeoNames country file.
"""

from __future__ import annotations

import difflib
import geonamescache

# ──────────────────────────────────────────────────────────────────────────────
# India state name -> GeoNames admin1 code
# (geonamescache stores states only as numeric codes, so we translate names.)
# ──────────────────────────────────────────────────────────────────────────────

INDIA_ADMIN1 = {
    "andaman and nicobar islands": "01",
    "andhra pradesh": "02",
    "arunachal pradesh": "30",
    "assam": "03",
    "bihar": "34",
    "chandigarh": "05",
    "chhattisgarh": "37",
    "dadra and nagar haveli": "06",
    "daman and diu": "07",
    "delhi": "07",          # NCT of Delhi
    "goa": "33",
    "gujarat": "09",
    "haryana": "10",
    "himachal pradesh": "11",
    "jammu and kashmir": "12",
    "jharkhand": "38",
    "karnataka": "19",
    "kerala": "13",
    "ladakh": "12",
    "lakshadweep": "14",
    "madhya pradesh": "35",
    "maharashtra": "16",
    "manipur": "17",
    "meghalaya": "18",
    "mizoram": "31",
    "nagaland": "20",
    "odisha": "21",
    "orissa": "21",         # old name
    "puducherry": "22",
    "pondicherry": "22",    # old name
    "punjab": "23",
    "rajasthan": "24",
    "sikkim": "29",
    "tamil nadu": "25",
    "telangana": "40",
    "tripura": "26",
    "uttar pradesh": "36",
    "uttarakhand": "39",
    "uttaranchal": "39",    # old name
    "west bengal": "28",
}

# Common country aliases -> ISO country code
COUNTRY_ALIASES = {
    "india": "IN", "bharat": "IN",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "britain": "GB",
    "usa": "US", "us": "US", "united states": "US", "america": "US",
    "uae": "AE", "united arab emirates": "AE",
    "nepal": "NP", "bangladesh": "BD", "pakistan": "PK", "sri lanka": "LK",
    "canada": "CA", "australia": "AU",
}

# Load the bundled dataset once at import time.
_gc = geonamescache.GeonamesCache()
_CITIES = list(_gc.get_cities().values())

# Pre-build a lowercase name index for fast exact matching.
# A name can map to multiple cities (e.g. several "Springfield"s).
_NAME_INDEX: dict[str, list[dict]] = {}
for _c in _CITIES:
    _NAME_INDEX.setdefault(_c["name"].lower(), []).append(_c)
    # Also index ascii alternatenames where present
    for _alt in _c.get("alternatenames", []):
        if _alt:
            _NAME_INDEX.setdefault(_alt.lower(), []).append(_c)

# A flat list of all known lowercase names, for fuzzy fallback.
_ALL_NAMES = list(_NAME_INDEX.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_query(raw: str) -> tuple[str, str | None, str | None]:
    """
    Split 'Barbil, Odisha, India' into (city, state, country_code).
    Country and state are optional. Returns lowercase city name.

    Also handles space-separated input with no commas, e.g. 'barbil odisha',
    by peeling recognised state/country words off the end of the string.
    """
    raw = raw.strip()
    if not raw:
        return "", None, None

    state = None
    country = None

    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        # No commas: try to detect a trailing state/country word.
        # Check the last 1-3 words against known state/country names.
        words = raw.split()
        parts = [raw]  # default: whole thing is the city
        for n in (3, 2, 1):  # longest match first ("andhra pradesh")
            if len(words) > n:
                tail = " ".join(words[-n:]).lower()
                head = " ".join(words[:-n])
                if tail in INDIA_ADMIN1 or tail in COUNTRY_ALIASES:
                    parts = [head, tail]
                    break

    city = parts[0].lower()

    # Walk the remaining parts; classify each as country or state.
    for token in parts[1:]:
        tok = token.lower()
        if tok in COUNTRY_ALIASES:
            country = COUNTRY_ALIASES[tok]
        elif tok in INDIA_ADMIN1:
            state = INDIA_ADMIN1[tok]
            country = country or "IN"
        else:
            # Unrecognised token — keep as a possible state name for India.
            if state is None:
                state = INDIA_ADMIN1.get(tok)

    return city, state, country


def _pick_best(candidates: list[dict],
               admin1: str | None,
               country: str | None,
               strict: bool = False) -> dict | None:
    """
    From a list of same-named cities, choose the best match using the
    state/country hints, then highest population as a tiebreaker.

    When `strict` is True (used for fuzzy matches), a state or country hint
    MUST be satisfied — otherwise we return None rather than guess wrongly.
    This prevents a misspelled 'Barbeel, Odisha' from matching a same-sounding
    town in another country.
    """
    if not candidates:
        return None

    pool = candidates

    # Narrow by country if we have one.
    if country:
        narrowed = [c for c in pool if c["countrycode"] == country]
        if narrowed:
            pool = narrowed
        elif strict:
            return None

    # Narrow by state (admin1) if we have one.
    if admin1:
        narrowed = [c for c in pool if c.get("admin1code") == admin1]
        if narrowed:
            pool = narrowed
        elif strict:
            return None

    # Tiebreak: most populous wins (usually the place people mean).
    return max(pool, key=lambda c: c.get("population", 0))


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def city_to_latlon(city: str) -> tuple[float, float] | None:
    """
    Resolve a place string to (lat, lon) using only bundled offline data.
    Returns None if no reasonable match is found.
    """
    if not city or not city.strip():
        return None

    name, admin1, country = _parse_query(city)

    # 1. Exact name match (with state/country disambiguation).
    if name in _NAME_INDEX:
        best = _pick_best(_NAME_INDEX[name], admin1, country)
        if best:
            return float(best["latitude"]), float(best["longitude"])

    # 2. Fuzzy match on the city name (handles minor spelling/diacritics).
    close = difflib.get_close_matches(name, _ALL_NAMES, n=5, cutoff=0.85)
    fuzzy_candidates: list[dict] = []
    for nm in close:
        fuzzy_candidates.extend(_NAME_INDEX[nm])
    if fuzzy_candidates:
        best = _pick_best(fuzzy_candidates, admin1, country, strict=True)
        if best:
            return float(best["latitude"]), float(best["longitude"])

    return None


def city_details(city: str) -> dict | None:
    """Same as city_to_latlon but returns the full record (name, pop, tz, ...)."""
    if not city or not city.strip():
        return None
    name, admin1, country = _parse_query(city)
    if name in _NAME_INDEX:
        best = _pick_best(_NAME_INDEX[name], admin1, country)
        if best:
            return best
    close = difflib.get_close_matches(name, _ALL_NAMES, n=5, cutoff=0.85)
    cands: list[dict] = []
    for nm in close:
        cands.extend(_NAME_INDEX[nm])
    return _pick_best(cands, admin1, country, strict=True) if cands else None


# ──────────────────────────────────────────────────────────────────────────────
# NOTE — if you need every small village (population < 15,000):
#
# geonamescache only bundles cities with population >= 15,000. To cover
# everything, download the full India file once and build a SQLite DB:
#
#   1. https://download.geonames.org/export/dump/IN.zip   (all India places)
#   2. Parse the tab-separated IN.txt (columns: geonameid, name, asciiname,
#      alternatenames, latitude, longitude, ... , admin1code, ..., population).
#   3. INSERT into a SQLite table with an index on lower(name) + admin1code,
#      commit the .db file to your repo, and query it the same way as above.
#
# The matching logic in this file (parse → exact → state-narrow → fuzzy) works
# identically against a SQLite source; only the data loading changes.
# ──────────────────────────────────────────────────────────────────────────────
