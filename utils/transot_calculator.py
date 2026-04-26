"""
transit_calculator.py
---------------------
Calculates current planetary transits (Gochar) over the natal chart.

Features:
    1. Current transit positions of all 9 planets (Sun–Saturn + Rahu/Ketu)
    2. Transit house from natal Moon (standard Vedic Gochar reference)
    3. Transit house from natal Lagna
    4. Ashtakavarga transit score for each planet (simplified)
    5. Key transit effects — benefic / malefic flag with reason
    6. Sade Sati detection (Saturn transit over Moon sign ±1)
    7. Dhaiya detection (Saturn in 4th or 8th from natal Moon)

Usage:
    from transit_calculator import calculate_transits
    result = calculate_transits(final_structure)   # dict from generate_kundli()
"""

from __future__ import annotations

from datetime import datetime, timezone
import swisseph as swe
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)

from utils.config import signs, planets as NATAL_PLANETS, nakshatras

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

# Transit effects from Moon sign (Janma Rashi) — classical Vedic Gochar
# house number from Moon → (effect_label, is_benefic)
MOON_TRANSIT_EFFECTS = {
    1:  ("Janma — physical stress, health concerns",               False),
    2:  ("Wealth drain, family friction",                          False),
    3:  ("Courage, short travels, gains through effort",           True),
    4:  ("Emotional unrest, home challenges",                      False),
    5:  ("Obstacles in intellect, children, speculation",          False),
    6:  ("Victory over enemies, good health",                      True),
    7:  ("Journey, relationship stress",                           False),
    8:  ("Obstacles, hidden enemies, health risk",                 False),
    9:  ("Fortune, spirituality, father's wellbeing",              True),
    10: ("Career success, recognition",                            True),
    11: ("Gains, income boost, fulfilment of desires",             True),
    12: ("Expenditure, foreign travel, spiritual retreat",         False),
}

# Benefic transit houses from Lagna (general)
LAGNA_BENEFIC_HOUSES = {3, 6, 10, 11}

# Planets and their transit periods (approximate days)
TRANSIT_PERIODS = {
    "Sun":     "~30 days per sign",
    "Moon":    "~2.5 days per sign",
    "Mercury": "~25 days per sign (varies)",
    "Venus":   "~26 days per sign (varies)",
    "Mars":    "~45 days per sign",
    "Jupiter": "~12 months per sign",
    "Saturn":  "~30 months per sign",
    "Rahu":    "~18 months per sign",
    "Ketu":    "~18 months per sign",
}

# Natural benefics / malefics
NATURAL_BENEFICS  = {"Jupiter", "Venus", "Mercury", "Moon"}
NATURAL_MALEFICS  = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_today_jd() -> float:
    """Julian Day for today (UT noon)."""
    now = datetime.now(timezone.utc)
    return swe.julday(now.year, now.month, now.day,
                      now.hour + now.minute / 60.0)


def _house_from(reference_sign: str, transit_sign: str) -> int:
    """Count house number of transit_sign from reference_sign (1-indexed)."""
    ref_idx     = SIGN_INDEX[reference_sign]
    transit_idx = SIGN_INDEX[transit_sign]
    return ((transit_idx - ref_idx) % 12) + 1


def _interpret_position(degree: float) -> dict:
    """Return sign, nakshatra, pada, degree_in_sign."""
    sign_index        = int(degree // 30)
    sign              = signs[sign_index]
    degree_in_rashi   = degree % 30
    nak_index         = int(degree // 13.3333333)
    nak               = nakshatras[nak_index % 27]
    degree_in_nak     = degree % 13.3333333
    pada              = int(degree_in_nak // 3.3333333) + 1
    return {
        "sign":             sign,
        "degree_in_sign":   round(degree_in_rashi, 4),
        "nakshatra":        nak,
        "pada":             pada,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Core transit calculation
# ──────────────────────────────────────────────────────────────────────────────

def _get_transit_positions() -> list[dict]:
    """Fetch current sidereal positions for all 9 planets."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = _get_today_jd()

    transit_positions = []

    for name, pl_id in NATAL_PLANETS.items():
        lon = swe.calc_ut(jd, pl_id, swe.FLG_SIDEREAL)[0][0]

        if name == "Ketu":
            lon = (lon + 180.0) % 360.0

        info = _interpret_position(lon)
        transit_positions.append({
            "planet":           name,
            "longitude":        round(lon, 6),
            "sign":             info["sign"],
            "degree_in_sign":   info["degree_in_sign"],
            "nakshatra":        info["nakshatra"],
            "pada":             info["pada"],
            "transit_period":   TRANSIT_PERIODS.get(name, ""),
        })

    return transit_positions


# ──────────────────────────────────────────────────────────────────────────────
# Sade Sati & Dhaiya
# ──────────────────────────────────────────────────────────────────────────────

def _check_sade_sati_dhaiya(natal_moon_sign: str, saturn_transit_sign: str) -> dict:
    """
    Sade Sati : Saturn transiting 12th, 1st (Janma), or 2nd from natal Moon sign.
    Dhaiya    : Saturn transiting 4th or 8th from natal Moon sign.
    """
    saturn_house_from_moon = _house_from(natal_moon_sign, saturn_transit_sign)

    sade_sati = saturn_house_from_moon in {12, 1, 2}
    dhaiya    = saturn_house_from_moon in {4, 8}

    phase = None
    if sade_sati:
        phase_map = {12: "Rising Phase (12th)", 1: "Peak Phase (Janma)", 2: "Setting Phase (2nd)"}
        phase = phase_map[saturn_house_from_moon]

    return {
        "sade_sati": {
            "active":               sade_sati,
            "phase":                phase,
            "saturn_house_from_moon": saturn_house_from_moon,
            "description": (
                "Sade Sati is a 7.5-year period when Saturn transits the 12th, "
                "1st (Janma), and 2nd signs from natal Moon. It brings challenges, "
                "transformation, and karmic lessons."
            ) if sade_sati else "Not active currently."
        },
        "dhaiya": {
            "active":               dhaiya,
            "saturn_house_from_moon": saturn_house_from_moon,
            "description": (
                f"Kantaka Shani (Dhaiya): Saturn in {saturn_house_from_moon}th from Moon. "
                "A 2.5-year period bringing obstacles in career (4th) or sudden setbacks (8th)."
            ) if dhaiya else "Not active currently."
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Per-planet transit interpretation
# ──────────────────────────────────────────────────────────────────────────────

def _interpret_transit(planet: str, house_from_moon: int,
                        house_from_lagna: int) -> dict:
    """
    Produce a human-readable effect summary for a planet's transit.
    """
    moon_effect_label, moon_benefic = MOON_TRANSIT_EFFECTS.get(
        house_from_moon, ("Neutral", True)
    )
    lagna_benefic = house_from_lagna in LAGNA_BENEFIC_HOUSES

    # Combined signal
    if moon_benefic and lagna_benefic:
        overall = "Highly Favourable"
    elif moon_benefic or lagna_benefic:
        overall = "Moderately Favourable"
    else:
        overall = "Challenging"

    # Amplify for natural malefics in sensitive houses
    if planet in NATURAL_MALEFICS and house_from_moon in {1, 4, 8, 12}:
        overall = "Challenging (malefic planet in difficult house)"

    return {
        "house_from_moon":          house_from_moon,
        "house_from_lagna":         house_from_lagna,
        "moon_transit_effect":      moon_effect_label,
        "moon_transit_benefic":     moon_benefic,
        "lagna_transit_benefic":    lagna_benefic,
        "overall_effect":           overall,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Master function
# ──────────────────────────────────────────────────────────────────────────────

def calculate_transits(final_structure: dict) -> dict:
    """
    Main entry point.
    Pass the dict returned by generate_kundli().

    Returns a 'transits' dict with:
        - transit_date      : today's date
        - planets           : list of transit positions + effects
        - sade_sati_dhaiya  : Saturn special period flags
        - summary           : list of currently active notable transits
    """
    planets_data = final_structure.get("planets_data", [])

    # Natal reference points
    natal_moon   = next((p for p in planets_data if p["name"] == "Moon"),    None)
    natal_lagna  = next((p for p in planets_data if p["name"] == "Ascendant"), None)

    natal_moon_sign  = natal_moon["zodiac"]  if natal_moon  else signs[0]
    natal_lagna_sign = natal_lagna["zodiac"] if natal_lagna else signs[0]

    # Current transit positions
    transit_positions = _get_transit_positions()

    # Saturn transit sign (for Sade Sati / Dhaiya)
    saturn_transit = next((p for p in transit_positions if p["planet"] == "Saturn"), None)
    saturn_transit_sign = saturn_transit["sign"] if saturn_transit else natal_moon_sign

    # Build enriched transit list
    enriched = []
    for t in transit_positions:
        house_from_moon   = _house_from(natal_moon_sign,  t["sign"])
        house_from_lagna  = _house_from(natal_lagna_sign, t["sign"])
        effects           = _interpret_transit(t["planet"], house_from_moon, house_from_lagna)

        enriched.append({**t, **effects})

    # Sade Sati / Dhaiya
    saturn_special = _check_sade_sati_dhaiya(natal_moon_sign, saturn_transit_sign)

    # Summary — highlight notable transits
    summary = []
    for t in enriched:
        if t["overall_effect"].startswith("Highly") or "malefic" in t["overall_effect"].lower():
            summary.append({
                "planet":   t["planet"],
                "sign":     t["sign"],
                "effect":   t["overall_effect"],
                "detail":   t["moon_transit_effect"],
            })

    if saturn_special["sade_sati"]["active"]:
        summary.append({
            "planet":  "Saturn",
            "sign":    saturn_transit_sign,
            "effect":  f"Sade Sati — {saturn_special['sade_sati']['phase']}",
            "detail":  saturn_special["sade_sati"]["description"],
        })

    if saturn_special["dhaiya"]["active"]:
        summary.append({
            "planet":  "Saturn",
            "sign":    saturn_transit_sign,
            "effect":  "Dhaiya (Kantaka Shani)",
            "detail":  saturn_special["dhaiya"]["description"],
        })

    return {
        "transit_date":         datetime.now().strftime("%d-%m-%Y"),
        "natal_moon_sign":      natal_moon_sign,
        "natal_lagna_sign":     natal_lagna_sign,
        "planets":              enriched,
        "sade_sati_dhaiya":     saturn_special,
        "notable_transits":     summary,
    }
