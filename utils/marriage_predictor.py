"""
marriage_predictor.py
---------------------
Vedic Astrology Marriage Prediction Module

Primary Sources:
  - P.V.R. Narasimha Rao, "Vedic Astrology: An Integrated Approach"
  - Classical Parasara / Jaimini traditions

Covers:
  1.  Upapada Lagna (UL) — marriage & spouse quality
  2.  Dara Karaka (DK) — chara karaka for spouse
  3.  7th house analysis  (D1 + D9)
  4.  Darapada / A7 — nature of one's social / romantic circle
  5.  Venus & 7th-from-Venus analysis
  6.  Marriage timing signals (Dasha + transit triggers)
  7.  Divorce / separation indicators
  8.  Marriage quality & spouse description
  9.  Delay / denial indicators
  10. Summary verdict

Usage:
    from marriage_predictor import predict_marriage
    result = predict_marriage(final_structure)
"""

from __future__ import annotations
from typing import Any

from utils.config import signs, DASHA_SEQUENCE

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

KENDRA_HOUSES = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}
DUSTHANA_HOUSES = {6, 8, 12}

NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
NATURAL_MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

# Exaltation / own-sign reference for strength checks
EXALTED_SIGN = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer",
    "Venus": "Pisces", "Saturn": "Libra",
}
DEBILITATED_SIGN = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn",
    "Venus": "Virgo", "Saturn": "Aries",
}
OWN_SIGNS = {
    "Sun": {"Leo"}, "Moon": {"Cancer"},
    "Mars": {"Aries", "Scorpio"}, "Mercury": {"Gemini", "Virgo"},
    "Jupiter": {"Sagittarius", "Pisces"},
    "Venus": {"Taurus", "Libra"}, "Saturn": {"Capricorn", "Aquarius"},
}
SIGN_LORD = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# Planet descriptions for spouse characteristics (UL occupants)
PLANET_SPOUSE_DESC = {
    "Sun": "charming, from a respectable / royal family, authoritative",
    "Moon": "gentle, nurturing, emotional, possibly fair-complexioned",
    "Mars": "bold and energetic (good); quarrelsome and aggressive (afflicted)",
    "Mercury": "intelligent, communicative, witty (good); indecisive (afflicted)",
    "Jupiter": "wise, noble, well-educated, spiritual, generous",
    "Venus": "beautiful/handsome, artistic, luxury-loving, refined",
    "Saturn": "disciplined, older or serious, may have delays in marriage",
    "Rahu": "unconventional, foreign connection, ambitious (good); deceptive (bad)",
    "Ketu": "spiritual, detached (good); short-tempered, eccentric (afflicted)",
}


# ─────────────────────────────────────────────────────────────────────────────
# Generic helpers
# ─────────────────────────────────────────────────────────────────────────────

def _planet_map(planets_data: list) -> dict:
    return {p["name"]: p for p in planets_data}


def _house_of(planet: str, chart: dict) -> int | None:
    for h, occupants in chart.items():
        for p in occupants:
            if p["name"] == planet:
                return int(h)
    return None


def _planets_in_house(house_num: int, chart: dict) -> list[str]:
    return [p["name"] for p in chart.get(str(house_num), [])]


def _sign_of_house(lagna_sign: str, house_num: int) -> str:
    idx = SIGN_INDEX[lagna_sign]
    return signs[(idx + house_num - 1) % 12]


def _lord_of_sign(sign: str) -> str:
    return SIGN_LORD[sign]


def _relative_house(from_sign: str, to_sign: str) -> int:
    """How many houses is to_sign from from_sign (1-indexed)?"""
    return (SIGN_INDEX[to_sign] - SIGN_INDEX[from_sign]) % 12 + 1


def _planet_strength_label(planet: str, sign: str) -> str:
    if sign == EXALTED_SIGN.get(planet):
        return "exalted"
    if sign in OWN_SIGNS.get(planet, set()):
        return "own sign"
    if sign == DEBILITATED_SIGN.get(planet):
        return "debilitated"
    return "neutral"


def _lagna_sign(planets_data: list) -> str | None:
    for p in planets_data:
        if p["name"] == "Ascendant":
            return p["zodiac"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Upapada Lagna (UL) — arudha pada of 12th house
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_upapada(lagna_sign: str, planets_data: list) -> str:
    """
    Arudha pada algorithm (Parasara):
      1. Start from 12th-house sign.
      2. Count to its lord's sign.
      3. Count the same number again from the lord's sign.
      4. Exception: if result falls in 1st or 7th from the 12th-house sign,
         take the 10th from the result instead.
    """
    # 12th house sign
    house_12_sign = _sign_of_house(lagna_sign, 12)
    pm = _planet_map(planets_data)

    lord_12 = SIGN_LORD[house_12_sign]
    lord_sign = pm[lord_12]["zodiac"] if lord_12 in pm else house_12_sign

    # Count from house_12_sign to lord_sign
    steps = (SIGN_INDEX[lord_sign] - SIGN_INDEX[house_12_sign]) % 12
    if steps == 0:
        steps = 12

    # Count same steps from lord_sign
    result_idx = (SIGN_INDEX[lord_sign] + steps - 1) % 12
    result_sign = signs[result_idx]

    # Exception rule
    pos_from_12 = _relative_house(house_12_sign, result_sign)
    if pos_from_12 in (1, 7):
        result_sign = signs[(result_idx + 9) % 12]  # 10th from result

    return result_sign


def analyze_upapada(lagna_sign: str, planets_data: list, d1: dict) -> dict:
    """
    Analyze Upapada Lagna (UL) for marriage quality, spouse nature,
    marriage longevity, and separation risks.

    Source: Narasimha Rao, Ch. 9 (Arudha Padas)
    """
    ul_sign = _calculate_upapada(lagna_sign, planets_data)
    pm = _planet_map(planets_data)

    # Planets in UL sign
    planets_in_ul = [
        p["name"] for p in planets_data
        if p["zodiac"] == ul_sign and p["name"] != "Ascendant"
    ]

    # House number of UL from lagna
    ul_house_from_lagna = _relative_house(lagna_sign, ul_sign)

    # 2nd from UL (end of marriage indicator)
    ul_2nd_sign = signs[(SIGN_INDEX[ul_sign] + 1) % 12]
    # 7th from UL (separation indicator)
    ul_7th_sign = signs[(SIGN_INDEX[ul_sign] + 6) % 12]
    # 8th from UL (longevity of marriage)
    ul_8th_sign = signs[(SIGN_INDEX[ul_sign] + 7) % 12]

    planets_in_ul_2nd = [p["name"] for p in planets_data if p["zodiac"] == ul_2nd_sign and p["name"] != "Ascendant"]
    planets_in_ul_7th = [p["name"] for p in planets_data if p["zodiac"] == ul_7th_sign and p["name"] != "Ascendant"]
    planets_in_ul_8th = [p["name"] for p in planets_data if p["zodiac"] == ul_8th_sign and p["name"] != "Ascendant"]

    # Spouse descriptions from UL occupants
    spouse_traits = []
    for p in planets_in_ul:
        if p in PLANET_SPOUSE_DESC:
            spouse_traits.append(f"{p}: {PLANET_SPOUSE_DESC[p]}")

    # Marriage longevity assessment
    longevity_notes = []
    malefics_8th_ul = [p for p in planets_in_ul_8th if p in NATURAL_MALEFICS]
    benefics_8th_ul = [p for p in planets_in_ul_8th if p in NATURAL_BENEFICS]

    if benefics_8th_ul:
        longevity_notes.append(f"Benefic(s) {benefics_8th_ul} in 8th from UL → long, stable marriage")
    if malefics_8th_ul:
        longevity_notes.append(
            f"Malefic(s) {malefics_8th_ul} in 8th from UL → challenges to marriage longevity"
        )
    if not planets_in_ul_8th:
        longevity_notes.append("8th from UL is empty → neutral marriage longevity")

    # Separation / divorce risks (2nd and 7th from UL)
    separation_risks = []
    malefics_2nd_ul = [p for p in planets_in_ul_2nd if p in NATURAL_MALEFICS]
    malefics_7th_ul = [p for p in planets_in_ul_7th if p in NATURAL_MALEFICS]

    if malefics_2nd_ul:
        separation_risks.append(
            f"Malefic(s) {malefics_2nd_ul} in 2nd from UL → risk of separation / end of marriage"
        )
    if malefics_7th_ul:
        separation_risks.append(
            f"Malefic(s) {malefics_7th_ul} in 7th from UL → risk of separation / end of marriage"
        )

    # UL lord strength
    ul_lord = SIGN_LORD[ul_sign]
    ul_lord_sign = pm.get(ul_lord, {}).get("zodiac", "unknown")
    ul_lord_strength = _planet_strength_label(ul_lord, ul_lord_sign) if ul_lord_sign != "unknown" else "unknown"

    return {
        "ul_sign": ul_sign,
        "ul_house_from_lagna": ul_house_from_lagna,
        "ul_lord": ul_lord,
        "ul_lord_sign": ul_lord_sign,
        "ul_lord_strength": ul_lord_strength,
        "planets_in_ul": planets_in_ul,
        "spouse_traits_from_ul": spouse_traits,
        "marriage_longevity": {
            "8th_from_ul_sign": ul_8th_sign,
            "planets_in_8th_from_ul": planets_in_ul_8th,
            "notes": longevity_notes,
        },
        "separation_risk": {
            "2nd_from_ul": ul_2nd_sign,
            "7th_from_ul": ul_7th_sign,
            "malefics_2nd_from_ul": malefics_2nd_ul,
            "malefics_7th_from_ul": malefics_7th_ul,
            "risks": separation_risks,
        },
        "description": (
            "Upapada Lagna (UL) is the arudha pada of the 12th house. "
            "It shows the nature of marriage and the quality of the spouse. "
            "Planets in UL describe the spouse. "
            "Benefics in 8th from UL indicate a long marriage; malefics there threaten longevity. "
            "Malefics in the 2nd or 7th from UL risk separation or divorce."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dara Karaka (DK) — chara karaka for spouse
# ─────────────────────────────────────────────────────────────────────────────

def _find_dara_karaka(planets_data: list) -> dict | None:
    """
    Dara Karaka = planet with the LOWEST degree in its sign
    (in Jaimini chara karaka system, 8 karakas version using Rahu).
    DK represents the spouse directly (not 7th from DK).

    Source: Narasimha Rao, Ch. 8 (Karakas)
    """
    karaka_planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu"]
    pm = {p["name"]: p for p in planets_data if p["name"] in karaka_planets}

    # Sort by degree_in_rashi descending → rank 1=AK ... rank 8=DK
    sorted_planets = sorted(pm.values(), key=lambda x: x["degree_in_rashi"], reverse=True)

    if len(sorted_planets) >= 8:
        dk = sorted_planets[7]  # 8th = DK
    elif sorted_planets:
        dk = sorted_planets[-1]
    else:
        return None

    return {
        "planet": dk["name"],
        "zodiac": dk["zodiac"],
        "degree_in_rashi": dk["degree_in_rashi"],
        "nakshatra": dk.get("Nakshatra", ""),
        "strength": _planet_strength_label(dk["name"], dk["zodiac"]),
    }


def analyze_dara_karaka(planets_data: list, d1: dict, d9: dict) -> dict:
    """
    DK directly represents the spouse. Its house, sign, and strength
    give clues about the spouse's personality and the marriage quality.

    Source: Narasimha Rao, Ch. 8
    """
    dk = _find_dara_karaka(planets_data)
    if not dk:
        return {"error": "Could not compute Dara Karaka"}

    dk_house_d1 = _house_of(dk["planet"], d1)
    dk_house_d9 = _house_of(dk["planet"], d9)

    # Is DK afflicted by malefics in D1?
    conjunct_planets_d1 = _planets_in_house(dk_house_d1, d1) if dk_house_d1 else []
    malefic_conjuncts = [p for p in conjunct_planets_d1 if p in NATURAL_MALEFICS and p != dk["planet"]]
    benefic_conjuncts = [p for p in conjunct_planets_d1 if p in NATURAL_BENEFICS and p != dk["planet"]]

    affliction_notes = []
    if malefic_conjuncts:
        affliction_notes.append(f"DK conjunct malefic(s) {malefic_conjuncts} in D1 → spouse may face struggles")
    if benefic_conjuncts:
        affliction_notes.append(f"DK conjunct benefic(s) {benefic_conjuncts} in D1 → spouse well-supported")
    if dk["strength"] == "exalted":
        affliction_notes.append(f"DK ({dk['planet']}) exalted → strong, noble spouse")
    elif dk["strength"] == "debilitated":
        affliction_notes.append(f"DK ({dk['planet']}) debilitated → spouse may face hardships; marriage needs care")

    return {
        "dara_karaka_planet": dk["planet"],
        "sign": dk["zodiac"],
        "degree_in_sign": round(dk["degree_in_rashi"], 2),
        "nakshatra": dk["nakshatra"],
        "strength": dk["strength"],
        "house_in_d1": dk_house_d1,
        "house_in_d9": dk_house_d9,
        "spouse_trait": PLANET_SPOUSE_DESC.get(dk["planet"], ""),
        "conjunct_in_d1": conjunct_planets_d1,
        "notes": affliction_notes,
        "description": (
            "Dara Karaka (DK) is the planet with the lowest degree among all planets. "
            "It is the chara karaka representing the spouse. "
            "DK itself shows the spouse — unlike Venus where we use the 7th from Venus. "
            "Its sign and house placement describe the spouse's nature and life circumstances."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. 7th House Analysis (D1 + D9)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_7th_house(lagna_sign: str, planets_data: list, d1: dict, d9: dict) -> dict:
    """
    Comprehensive 7th house analysis in both D1 (physical) and D9 (dharmic).

    Source: Narasimha Rao, Ch. 7 (Houses), Ch. 25 (Divisional Charts)
    """
    pm = _planet_map(planets_data)

    # ── D1 analysis ───────────────────────────────────────────────────────────
    house_7_sign_d1 = _sign_of_house(lagna_sign, 7)
    lord_7_d1 = SIGN_LORD[house_7_sign_d1]
    lord_7_d1_sign = pm.get(lord_7_d1, {}).get("zodiac", "unknown")
    lord_7_d1_house = _house_of(lord_7_d1, d1)
    lord_7_d1_strength = _planet_strength_label(lord_7_d1, lord_7_d1_sign)

    planets_in_7th_d1 = _planets_in_house(7, d1)
    malefics_in_7th_d1 = [p for p in planets_in_7th_d1 if p in NATURAL_MALEFICS]
    benefics_in_7th_d1 = [p for p in planets_in_7th_d1 if p in NATURAL_BENEFICS]

    d1_notes = []
    if benefics_in_7th_d1:
        d1_notes.append(f"Benefic(s) {benefics_in_7th_d1} in 7th → favourable for marriage and spouse")
    if malefics_in_7th_d1:
        d1_notes.append(f"Malefic(s) {malefics_in_7th_d1} in 7th → challenges in marriage or delays")
    if lord_7_d1_strength == "exalted":
        d1_notes.append(f"7th lord {lord_7_d1} is exalted → very strong marriage prospects")
    elif lord_7_d1_strength == "own sign":
        d1_notes.append(f"7th lord {lord_7_d1} in own sign → strong marriage prospects")
    elif lord_7_d1_strength == "debilitated":
        d1_notes.append(f"7th lord {lord_7_d1} debilitated → spouse may have struggles; marriage needs work")

    # 7th lord in dusthana?
    if lord_7_d1_house in DUSTHANA_HOUSES:
        d1_notes.append(
            f"7th lord in dusthana house {lord_7_d1_house} → friction in marriage; possible delays"
        )

    # ── D9 analysis ───────────────────────────────────────────────────────────
    # In D9, find the Ascendant's sign (lagna in navamsa)
    navamsa_lagna = None
    for p in planets_data:
        if p["name"] == "Ascendant":
            # D9 lagna needs to be read from house_mapper — we infer from d9 structure
            # The ascendant sign in D9 is the sign whose house_number=1 in d9 is empty
            # but we can use the sign of the lagna in D9 derived externally if available
            pass

    # Get 7th house occupants in D9
    planets_in_7th_d9 = _planets_in_house(7, d9)
    malefics_in_7th_d9 = [p for p in planets_in_7th_d9 if p in NATURAL_MALEFICS]
    benefics_in_7th_d9 = [p for p in planets_in_7th_d9 if p in NATURAL_BENEFICS]

    d9_notes = []
    if benefics_in_7th_d9:
        d9_notes.append(
            f"Benefic(s) {benefics_in_7th_d9} in 7th of D9 → inner harmony in marriage; supportive spouse"
        )
    if malefics_in_7th_d9:
        d9_notes.append(
            f"Malefic(s) {malefics_in_7th_d9} in 7th of D9 → dharmic tensions or conflicts in marriage"
        )

    # Venus in D9 7th → very auspicious for marriage
    if "Venus" in planets_in_7th_d9:
        d9_notes.append("Venus in 7th of D9 → highly auspicious; loving, beautiful spouse")

    # Jupiter in D9 7th → wise, noble spouse
    if "Jupiter" in planets_in_7th_d9:
        d9_notes.append("Jupiter in 7th of D9 → noble, spiritual, or educated spouse")

    # ── Venus placement ────────────────────────────────────────────────────────
    venus_sign = pm.get("Venus", {}).get("zodiac", "unknown")
    venus_house_d1 = _house_of("Venus", d1)
    venus_7th_sign = signs[(SIGN_INDEX[venus_sign] + 6) % 12] if venus_sign != "unknown" else None

    venus_notes = []
    if venus_house_d1 == 7:
        venus_notes.append("Venus in 7th house (D1) → strong indicator of marriage, attractive spouse")
    if venus_house_d1 in KENDRA_HOUSES:
        venus_notes.append(f"Venus in Kendra house {venus_house_d1} → favourable for marriage")
    venus_strength = _planet_strength_label("Venus", venus_sign) if venus_sign != "unknown" else "unknown"
    if venus_strength in ("exalted", "own sign"):
        venus_notes.append(f"Venus {venus_strength} → excellent marriage prospects, charming spouse")
    elif venus_strength == "debilitated":
        venus_notes.append("Venus debilitated (Virgo) → challenges in marriage / relationships")

    return {
        "d1": {
            "7th_house_sign": house_7_sign_d1,
            "7th_lord": lord_7_d1,
            "7th_lord_sign": lord_7_d1_sign,
            "7th_lord_house": lord_7_d1_house,
            "7th_lord_strength": lord_7_d1_strength,
            "planets_in_7th": planets_in_7th_d1,
            "notes": d1_notes,
        },
        "d9": {
            "planets_in_7th": planets_in_7th_d9,
            "notes": d9_notes,
        },
        "venus": {
            "sign": venus_sign,
            "house_d1": venus_house_d1,
            "strength": venus_strength,
            "7th_from_venus": venus_7th_sign,
            "notes": venus_notes,
        },
        "description": (
            "The 7th house is the primary house of marriage and spouse. "
            "Its sign, lord, and occupying planets in D1 show the physical aspects of marriage. "
            "D9 (Navamsa) is the prime chart for marriage — its 7th house shows the inner / dharmic dimension. "
            "Venus is the naisargika karaka (natural significator) of marriage; "
            "the 7th from Venus is also used for predicting marriage."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Darapada (A7) — arudha pada of 7th house
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_darapada(lagna_sign: str, planets_data: list) -> str:
    """
    A7 = arudha pada of 7th house.
    Shows the social circle and perceptions around one's relationships.
    """
    house_7_sign = _sign_of_house(lagna_sign, 7)
    pm = _planet_map(planets_data)

    lord_7 = SIGN_LORD[house_7_sign]
    lord_sign = pm[lord_7]["zodiac"] if lord_7 in pm else house_7_sign

    steps = (SIGN_INDEX[lord_sign] - SIGN_INDEX[house_7_sign]) % 12
    if steps == 0:
        steps = 12

    result_idx = (SIGN_INDEX[lord_sign] + steps - 1) % 12
    result_sign = signs[result_idx]

    pos_from_7 = _relative_house(house_7_sign, result_sign)
    if pos_from_7 in (1, 7):
        result_sign = signs[(result_idx + 9) % 12]

    return result_sign


def analyze_darapada(lagna_sign: str, planets_data: list, ul_sign: str) -> dict:
    """
    A7 shows the kinds of people one associates with, which shapes the
    perception of one's relationships. It complements UL analysis.

    Source: Narasimha Rao, Ch. 9
    """
    a7_sign = _calculate_darapada(lagna_sign, planets_data)
    pm = _planet_map(planets_data)

    planets_in_a7 = [
        p["name"] for p in planets_data
        if p["zodiac"] == a7_sign and p["name"] != "Ascendant"
    ]

    # Check AL-A7 relationship (affects Raja Yoga effectiveness)
    al_sign = None
    lagna_lord = SIGN_LORD[lagna_sign]
    lord_sign = pm.get(lagna_lord, {}).get("zodiac", lagna_sign)
    steps = (SIGN_INDEX[lord_sign] - SIGN_INDEX[lagna_sign]) % 12
    if steps == 0:
        steps = 12
    result_idx = (SIGN_INDEX[lord_sign] + steps - 1) % 12
    result_sign = signs[result_idx]
    pos_from_lagna = _relative_house(lagna_sign, result_sign)
    if pos_from_lagna in (1, 7):
        al_sign = signs[(result_idx + 9) % 12]
    else:
        al_sign = result_sign

    al_a7_relationship = _relative_house(al_sign, a7_sign)
    notes = []
    if al_a7_relationship in (2, 12):
        notes.append(
            "AL and A7 are in 2/12 relationship → Raja Yogas in chart may be less effective in the material domain"
        )
    elif al_a7_relationship in (6, 8):
        notes.append(
            "AL and A7 are in 6/8 relationship → tension between public image and relationships"
        )
    else:
        notes.append("AL and A7 are in a good relationship → Raja Yogas manifest well")

    # A7 and UL relationship
    a7_ul_pos = _relative_house(a7_sign, ul_sign)
    if a7_ul_pos in (3,):
        notes.append("A7 is in 3rd from UL → social circle supports marriage")
    if a7_ul_pos in (8,):
        notes.append("A7 is in 8th from UL → secretive or transformative relationships before marriage")

    return {
        "a7_sign": a7_sign,
        "planets_in_a7": planets_in_a7,
        "al_sign": al_sign,
        "al_a7_house_distance": al_a7_relationship,
        "notes": notes,
        "description": (
            "Darapada (A7) shows the kinds of people one associates with in romantic/social contexts. "
            "It shapes the world's perception of one's relationships. "
            "When AL and A7 are not in mutual 2nd/12th or 6th/8th, Raja Yogas are more effective."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Marriage Delay / Denial Indicators
# ─────────────────────────────────────────────────────────────────────────────

def analyze_marriage_delay(lagna_sign: str, planets_data: list, d1: dict, d9: dict) -> dict:
    """
    Standard Parasara / classical rules for delayed or denied marriage.
    """
    pm = _planet_map(planets_data)
    delay_factors = []
    denial_factors = []

    house_7_sign = _sign_of_house(lagna_sign, 7)
    lord_7 = SIGN_LORD[house_7_sign]
    lord_7_sign = pm.get(lord_7, {}).get("zodiac", "unknown")
    lord_7_house = _house_of(lord_7, d1)
    venus_house = _house_of("Venus", d1)
    saturn_house = _house_of("Saturn", d1)

    # Rule 1: 7th lord debilitated or in dusthana
    if lord_7_sign == DEBILITATED_SIGN.get(lord_7):
        delay_factors.append(f"7th lord {lord_7} debilitated → delays in marriage")
    if lord_7_house in DUSTHANA_HOUSES:
        delay_factors.append(f"7th lord {lord_7} in dusthana house {lord_7_house} → delays")

    # Rule 2: Saturn in 7th house
    if saturn_house == 7:
        delay_factors.append("Saturn in 7th house → classic indicator of delayed marriage")

    # Rule 3: Saturn aspecting Venus (3rd, 7th, 10th from Saturn)
    if saturn_house and venus_house:
        saturn_aspects = {
            (saturn_house + 2) % 12 + 1,
            (saturn_house + 6) % 12 + 1,
            (saturn_house + 9) % 12 + 1,
        }
        if venus_house in saturn_aspects:
            delay_factors.append(
                f"Saturn (house {saturn_house}) aspects Venus (house {venus_house}) → delay in marriage"
            )

    # Rule 4: Saturn aspecting 7th house
    if saturn_house:
        if 7 in saturn_aspects if saturn_house else False:
            delay_factors.append("Saturn aspects 7th house → delay or obstacles in marriage")

    # Rule 5: Rahu or Ketu in 7th house
    rahu_house = _house_of("Rahu", d1)
    ketu_house = _house_of("Ketu", d1)
    if rahu_house == 7:
        delay_factors.append("Rahu in 7th house → unconventional or delayed marriage")
    if ketu_house == 7:
        delay_factors.append("Ketu in 7th house → detachment from marriage; possible delay or denial")

    # Rule 6: Venus combust (very close to Sun — within 8°)
    venus_lon = pm.get("Venus", {}).get("longitude", -1)
    sun_lon = pm.get("Sun", {}).get("longitude", -1)
    if venus_lon >= 0 and sun_lon >= 0:
        diff = abs(venus_lon - sun_lon) % 360
        diff = min(diff, 360 - diff)
        if diff <= 8:
            delay_factors.append(
                f"Venus combust (within {round(diff, 1)}° of Sun) → weakened Venus; delays in marriage"
            )

    # Rule 7: Venus debilitated (Virgo)
    venus_sign = pm.get("Venus", {}).get("zodiac", "")
    if venus_sign == "Virgo":
        delay_factors.append("Venus debilitated in Virgo → challenges in finding a suitable partner")

    # Rule 8: 7th house in D9 occupied by multiple malefics
    malefics_7th_d9 = [p for p in _planets_in_house(7, d9) if p in NATURAL_MALEFICS]
    if len(malefics_7th_d9) >= 2:
        delay_factors.append(
            f"Multiple malefics {malefics_7th_d9} in 7th of D9 → repeated obstacles in marriage"
        )

    # Rule 9: Denial — lord of 7th and Venus both afflicted
    venus_afflicted = (venus_sign == DEBILITATED_SIGN.get("Venus")) or (venus_house in DUSTHANA_HOUSES)
    lord7_afflicted = (lord_7_sign == DEBILITATED_SIGN.get(lord_7)) or (lord_7_house in DUSTHANA_HOUSES)
    if venus_afflicted and lord7_afflicted:
        denial_factors.append(
            "Both Venus and 7th lord are afflicted → strong indication of difficulty in getting married"
        )

    severity = "None"
    if denial_factors:
        severity = "Denial risk"
    elif len(delay_factors) >= 3:
        severity = "Significant delay likely"
    elif len(delay_factors) >= 1:
        severity = "Some delay possible"

    return {
        "severity": severity,
        "delay_factors": delay_factors,
        "denial_factors": denial_factors,
        "description": (
            "Delay/denial indicators are assessed from the 7th lord's condition, Saturn's influence, "
            "Venus's strength, and the state of D9's 7th house. "
            "3+ factors together indicate significant delay. Combined affliction of Venus and 7th lord "
            "raises the risk of difficulty in marriage."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Multiple Marriages Indicator
# ─────────────────────────────────────────────────────────────────────────────

def analyze_multiple_marriages(lagna_sign: str, planets_data: list, d1: dict, ul_sign: str) -> dict:
    """
    Classical indicators for more than one marriage.
    """
    pm = _planet_map(planets_data)
    indicators = []

    # Rule 1: Multiple planets in 7th house (especially malefics)
    planets_7th = _planets_in_house(7, d1)
    if len(planets_7th) >= 2:
        indicators.append(
            f"Multiple planets {planets_7th} in 7th house → possible multiple marriages or partnerships"
        )

    # Rule 2: Venus in dual signs (Gemini, Virgo, Sagittarius, Pisces)
    venus_sign = pm.get("Venus", {}).get("zodiac", "")
    dual_signs = {"Gemini", "Virgo", "Sagittarius", "Pisces"}
    if venus_sign in dual_signs:
        indicators.append(
            f"Venus in dual sign ({venus_sign}) → tendency toward more than one union"
        )

    # Rule 3: 7th lord in dual sign
    house_7_sign = _sign_of_house(lagna_sign, 7)
    if house_7_sign in dual_signs:
        indicators.append(f"7th house in dual sign ({house_7_sign}) → possible multiple marriages")

    # Rule 4: Rahu in 7th or conjunct Venus
    rahu_house = _house_of("Rahu", d1)
    venus_house = _house_of("Venus", d1)
    if rahu_house == 7:
        indicators.append("Rahu in 7th house → unconventional marriage; possible second marriage")
    if rahu_house and venus_house and rahu_house == venus_house:
        indicators.append("Rahu conjunct Venus → strong desire nature; possible multiple relationships")

    # Rule 5: Malefics in UL and UL 8th
    ul_8th_sign = signs[(SIGN_INDEX[ul_sign] + 7) % 12]
    planets_ul_8th = [p["name"] for p in planets_data if p["zodiac"] == ul_8th_sign and p["name"] != "Ascendant"]
    malefics_ul = [p["name"] for p in planets_data if p["zodiac"] == ul_sign and p["name"] in NATURAL_MALEFICS]
    if malefics_ul and [p for p in planets_ul_8th if p in NATURAL_MALEFICS]:
        indicators.append(
            "Malefics in UL + malefics in 8th from UL → first marriage may end; second marriage possible"
        )

    return {
        "indicators": indicators,
        "risk": "Present" if len(indicators) >= 2 else "Low",
        "description": (
            "Multiple marriage indicators include dual signs for 7th house or Venus, "
            "Rahu's influence on 7th/Venus, multiple planets in 7th, "
            "and simultaneous affliction of UL and its 8th house."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Marriage Timing Signals (Dasha-based)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_dasha_date(date_str: str):
    """Parse dasha date string DD-MM-YYYY to datetime."""
    from datetime import datetime
    return datetime.strptime(date_str, "%d-%m-%Y")


def analyze_marriage_timing_dasha(
        lagna_sign: str, planets_data: list, d1: dict, d9: dict,
        ul_sign: str, all_dashas: list
) -> dict:
    """
    Identifies marriage-giving Dasha periods with THREE priority layers:

      LAYER 1 — CURRENT RUNNING PERIOD
        Checks if the CURRENTLY running Mahadasha/Antardasha/Pratyantar
        itself is a marriage-giving combination. If yes, marriage could
        happen right now or very soon.

      LAYER 2 — NEAR FUTURE (next ~10 years from today)
        Scans ALL Antardashas within the current + next Mahadasha that
        fall within the next 10 years, scored for marriage potential.
        This catches Jupiter/Venus antardashas inside a running Saturn dasha etc.

      LAYER 3 — ALL-TIME BEST
        The strongest marriage-giving Mahadasha periods across the
        entire lifespan (for reference).

    Scoring criteria (additive):
      +3  Planet is 7th lord in D1
      +3  Planet is Dara Karaka (DK)
      +2  Planet is Venus (natural significator)
      +2  Planet occupies a UL-trine sign (1st/3rd/8th from UL)
      +1  Planet is lagna lord
      +1  Planet is present in D9
      +2  Planet is strong (exalted/own sign) in D9

    Score ≥ 4 = Strong marriage-giving period
    Score 2–3 = Moderate — possible with supporting transits
    """
    from datetime import datetime, timedelta

    pm = _planet_map(planets_data)
    dk = _find_dara_karaka(planets_data)
    dk_planet = dk["planet"] if dk else None

    house_7_sign_d1 = _sign_of_house(lagna_sign, 7)
    lord_7_d1 = SIGN_LORD[house_7_sign_d1]
    lord_lagna = SIGN_LORD[lagna_sign]

    # UL trine signs: 1st (UL itself), 3rd from UL, 8th from UL
    ul_1st = ul_sign
    ul_3rd = signs[(SIGN_INDEX[ul_sign] + 2) % 12]
    ul_8th = signs[(SIGN_INDEX[ul_sign] + 7) % 12]
    ul_trine_signs = {ul_1st, ul_3rd, ul_8th}

    today = datetime.today()
    near_future_cutoff = today + timedelta(days=365 * 10)  # next 10 years

    def score_planet_for_marriage(planet_name: str) -> tuple[int, list[str]]:
        reasons = []
        score = 0
        p_data = pm.get(planet_name)

        if planet_name == lord_7_d1:
            score += 3
            reasons.append(f"7th lord in D1 ({lord_7_d1})")

        # Check presence and strength in D9
        p_sign_d9 = None
        for h, occupants in d9.items():
            for p in occupants:
                if p["name"] == planet_name:
                    p_sign_d9 = p["sign"]
        if p_sign_d9:
            score += 1
            reasons.append(f"Present in D9 ({p_sign_d9})")
            strength_d9 = _planet_strength_label(planet_name, p_sign_d9)
            if strength_d9 in ("exalted", "own sign"):
                score += 2
                reasons.append(f"Strong in D9 — {strength_d9}")

        if planet_name == "Venus":
            score += 2
            reasons.append("Venus — natural significator of marriage")

        if planet_name == dk_planet:
            score += 3
            reasons.append(f"Dara Karaka — chara karaka for spouse")

        if p_data and p_data["zodiac"] in ul_trine_signs:
            score += 2
            reasons.append(f"Occupies UL-trine sign {p_data['zodiac']}")

        if planet_name == lord_lagna:
            score += 1
            reasons.append("Lagna lord — supports all auspicious events")

        return score, reasons

    # ── LAYER 1: Current running period ──────────────────────────────────────
    current_period = None
    current_maha_planet = None
    current_antar_planet = None

    for maha in all_dashas:
        m_start = _parse_dasha_date(maha["start"])
        m_end = _parse_dasha_date(maha["end"])
        if m_start <= today <= m_end:
            current_maha_planet = maha["planet"]
            m_score, m_reasons = score_planet_for_marriage(maha["planet"])

            for antar in maha.get("antardasha", []):
                a_start = _parse_dasha_date(antar["start"])
                a_end = _parse_dasha_date(antar["end"])
                if a_start <= today <= a_end:
                    current_antar_planet = antar["planet"]
                    a_score, a_reasons = score_planet_for_marriage(antar["planet"])

                    # Check pratyantar
                    current_prat = None
                    for prat in antar.get("pratyantar", []):
                        p_start = _parse_dasha_date(prat["start"])
                        p_end = _parse_dasha_date(prat["end"])
                        if p_start <= today <= p_end:
                            p_score, p_reasons = score_planet_for_marriage(prat["planet"])
                            current_prat = {
                                "planet": prat["planet"],
                                "start": prat["start"],
                                "end": prat["end"],
                                "score": p_score,
                                "reasons": p_reasons,
                                "is_marriage_giving": p_score >= 3,
                            }
                            break

                    combined_score = m_score + a_score
                    current_period = {
                        "mahadasha": {
                            "planet": maha["planet"],
                            "start": maha["start"],
                            "end": maha["end"],
                            "score": m_score,
                            "reasons": m_reasons,
                        },
                        "antardasha": {
                            "planet": antar["planet"],
                            "start": antar["start"],
                            "end": antar["end"],
                            "score": a_score,
                            "reasons": a_reasons,
                        },
                        "pratyantar": current_prat,
                        "combined_score": combined_score,
                        "verdict": (
                            "⭐ STRONG — Marriage very likely in this period"
                            if combined_score >= 7
                            else "✅ GOOD — Marriage possible; watch supporting transits"
                            if combined_score >= 4
                            else "⚠️ MODERATE — Possible but needs strong transit support"
                            if combined_score >= 2
                            else "❌ WEAK — Current period not a strong marriage trigger"
                        ),
                    }
                    break
            break

    # ── LAYER 2: Near-future marriage windows (next 10 years) ────────────────
    near_future_windows = []

    for maha in all_dashas:
        m_start = _parse_dasha_date(maha["start"])
        m_end = _parse_dasha_date(maha["end"])

        # Only consider Mahadashas that overlap with the next 10 years
        if m_end < today or m_start > near_future_cutoff:
            continue

        m_score, m_reasons = score_planet_for_marriage(maha["planet"])

        for antar in maha.get("antardasha", []):
            a_start = _parse_dasha_date(antar["start"])
            a_end = _parse_dasha_date(antar["end"])

            # Only future or currently running antardashas, within 10 years
            if a_end < today or a_start > near_future_cutoff:
                continue

            a_score, a_reasons = score_planet_for_marriage(antar["planet"])
            combined = m_score + a_score

            if combined >= 4:  # Only meaningful combinations
                # Find the best pratyantar within this antardasha
                best_prat = None
                best_prat_score = 0
                for prat in antar.get("pratyantar", []):
                    p_start = _parse_dasha_date(prat["start"])
                    p_end = _parse_dasha_date(prat["end"])
                    if p_end < today:
                        continue
                    p_score, p_reasons = score_planet_for_marriage(prat["planet"])
                    if p_score > best_prat_score:
                        best_prat_score = p_score
                        best_prat = {
                            "planet": prat["planet"],
                            "start": prat["start"],
                            "end": prat["end"],
                            "score": p_score,
                            "reasons": p_reasons,
                        }

                is_current = (a_start <= today <= a_end)
                near_future_windows.append({
                    "mahadasha_planet": maha["planet"],
                    "mahadasha_start": maha["start"],
                    "mahadasha_end": maha["end"],
                    "antardasha_planet": antar["planet"],
                    "antardasha_start": antar["start"],
                    "antardasha_end": antar["end"],
                    "mahadasha_score": m_score,
                    "antardasha_score": a_score,
                    "combined_score": combined,
                    "is_currently_running": is_current,
                    "best_pratyantar": best_prat,
                    "mahadasha_reasons": m_reasons,
                    "antardasha_reasons": a_reasons,
                    "strength": (
                        "⭐ Very Strong" if combined >= 9
                        else "✅ Strong" if combined >= 6
                        else "🔶 Moderate" if combined >= 4
                        else "Low"
                    ),
                })

    # Sort: currently running first, then by combined score desc, then by start date
    near_future_windows.sort(
        key=lambda x: (
            0 if x["is_currently_running"] else 1,
            -x["combined_score"],
            x["antardasha_start"],
        )
    )

    # ── LAYER 3: All-time best Mahadashas (reference) ────────────────────────
    all_time_best = []
    for maha in all_dashas:
        m_score, m_reasons = score_planet_for_marriage(maha["planet"])
        if m_score >= 3:
            best_antardashas = []
            for antar in maha.get("antardasha", []):
                a_score, a_reasons = score_planet_for_marriage(antar["planet"])
                if a_score >= 2:
                    best_antardashas.append({
                        "planet": antar["planet"],
                        "start": antar["start"],
                        "end": antar["end"],
                        "score": a_score,
                        "reasons": a_reasons,
                    })
            all_time_best.append({
                "mahadasha_planet": maha["planet"],
                "mahadasha_start": maha["start"],
                "mahadasha_end": maha["end"],
                "mahadasha_score": m_score,
                "mahadasha_reasons": m_reasons,
                "top_antardashas": sorted(best_antardashas, key=lambda x: -x["score"])[:3],
            })
    all_time_best.sort(key=lambda x: -x["mahadasha_score"])

    return {
        "7th_lord_d1": lord_7_d1,
        "dk_planet": dk_planet,
        "ul_trine_signs": list(ul_trine_signs),

        "current_running_period": current_period,

        "near_future_marriage_windows": near_future_windows[:8],

        "all_time_best_mahadashas": all_time_best[:5],

        "description": (
            "Marriage timing uses THREE layers: "
            "(1) CURRENT PERIOD — is marriage possible right now? "
            "(2) NEAR FUTURE — all Maha+Antardasha windows in the next 10 years scored for marriage. "
            "This catches Jupiter/Venus antardashas inside a currently running Saturn/Rahu dasha. "
            "(3) ALL-TIME BEST — strongest Mahadasha periods for reference. "
            "Score = Maha score + Antardasha score. "
            "≥9 = Very Strong | ≥6 = Strong | ≥4 = Moderate. "
            "Always cross-check with Jupiter/Venus transits over natal 7th house and DK sign."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Transit Triggers for Marriage
# ─────────────────────────────────────────────────────────────────────────────

def analyze_marriage_transit_triggers(
        lagna_sign: str, planets_data: list, d1: dict
) -> dict:
    """
    Key natal positions that transiting planets should activate to trigger marriage.

    Source: Narasimha Rao, Ch. 25 (Transit Analysis)
    Key transit signals:
      - Jupiter transiting natal 7th house sign
      - Jupiter transiting natal Venus sign
      - Jupiter transiting natal DK sign
      - Venus transiting vivaha saham (if calculated)
      - 7th lord transiting close to natal Venus or 7th house
    """
    pm = _planet_map(planets_data)
    dk = _find_dara_karaka(planets_data)

    house_7_sign = _sign_of_house(lagna_sign, 7)
    venus_natal_sign = pm.get("Venus", {}).get("zodiac", "unknown")
    dk_natal_sign = dk["zodiac"] if dk else "unknown"

    triggers = []

    triggers.append({
        "trigger": "Jupiter transits natal 7th house sign",
        "watch_sign": house_7_sign,
        "planet": "Jupiter",
        "importance": "High",
        "note": "Jupiter activating the 7th house is the classic marriage transit",
    })
    triggers.append({
        "trigger": "Jupiter transits natal Venus sign",
        "watch_sign": venus_natal_sign,
        "planet": "Jupiter",
        "importance": "High",
        "note": "Jupiter over Venus — natural karaka activated",
    })
    if dk_natal_sign not in ("unknown",):
        triggers.append({
            "trigger": "Jupiter transits natal DK sign",
            "watch_sign": dk_natal_sign,
            "planet": "Jupiter",
            "importance": "High",
            "note": "Jupiter activating DK sign — spouse significator awakened",
        })
    triggers.append({
        "trigger": "7th lord transits natal Venus sign or natal 7th house",
        "watch_sign": f"{venus_natal_sign} or {house_7_sign}",
        "planet": SIGN_LORD[house_7_sign],
        "importance": "Medium",
        "note": "7th lord activating key marriage significators",
    })
    triggers.append({
        "trigger": "Venus transits natal 7th house sign",
        "watch_sign": house_7_sign,
        "planet": "Venus",
        "importance": "Medium",
        "note": "Venus activating the 7th house — marriage significator in marriage house",
    })

    return {
        "natal_7th_sign": house_7_sign,
        "natal_venus_sign": venus_natal_sign,
        "natal_dk_sign": dk_natal_sign,
        "transit_triggers": triggers,
        "description": (
            "During a favourable Dasha period, marriage is most likely when "
            "transiting Jupiter activates: (1) natal 7th house sign, (2) natal Venus sign, "
            "(3) natal DK sign. "
            "Cross-check with Navamsa Narayana Dasa for fine-tuned timing. "
            "Transit of 7th lord or Venus over natal marriage significators confirms timing."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Divorce / Separation Indicators (detailed)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_divorce_indicators(
        lagna_sign: str, planets_data: list, d1: dict, d9: dict, ul_sign: str
) -> dict:
    """
    Divorce/separation indicators from D1, UL, and D9.

    Source: Narasimha Rao, Ch. 9 (UL), Ch. 24 (Kalachakra Dasa example),
            Exercise 36 in the book.
    """
    pm = _planet_map(planets_data)
    indicators = []

    # From UL: 2nd and 7th from UL are "end of marriage" houses
    ul_2nd = signs[(SIGN_INDEX[ul_sign] + 1) % 12]
    ul_7th = signs[(SIGN_INDEX[ul_sign] + 6) % 12]
    ul_8th = signs[(SIGN_INDEX[ul_sign] + 7) % 12]

    malefics_ul_2nd = [p["name"] for p in planets_data if p["zodiac"] == ul_2nd and p["name"] in NATURAL_MALEFICS]
    malefics_ul_7th = [p["name"] for p in planets_data if p["zodiac"] == ul_7th and p["name"] in NATURAL_MALEFICS]
    malefics_ul_8th = [p["name"] for p in planets_data if p["zodiac"] == ul_8th and p["name"] in NATURAL_MALEFICS]
    benefics_ul_8th = [p["name"] for p in planets_data if p["zodiac"] == ul_8th and p["name"] in NATURAL_BENEFICS]

    if malefics_ul_2nd:
        indicators.append(f"Malefics {malefics_ul_2nd} in 2nd from UL → end-of-marriage risk (separation/divorce)")
    if malefics_ul_7th:
        indicators.append(f"Malefics {malefics_ul_7th} in 7th from UL → end-of-marriage risk (separation/divorce)")
    if malefics_ul_8th and not benefics_ul_8th:
        indicators.append(
            f"Malefics {malefics_ul_8th} in 8th from UL without benefic support → marriage longevity threatened"
        )

    # 6th and 8th from lagna bring marital troubles
    planets_6th = _planets_in_house(6, d1)
    planets_8th = _planets_in_house(8, d1)
    malefics_6th = [p for p in planets_6th if p in NATURAL_MALEFICS]
    malefics_8th = [p for p in planets_8th if p in NATURAL_MALEFICS]

    if malefics_6th:
        indicators.append(
            f"Malefics {malefics_6th} in 6th house → conflict and disputes in marriage"
        )
    if malefics_8th:
        indicators.append(
            f"Malefics {malefics_8th} in 8th house → sudden upheavals or hidden tensions in marriage"
        )

    # Saturn + Mars both afflicting 7th
    saturn_house = _house_of("Saturn", d1)
    mars_house = _house_of("Mars", d1)
    if saturn_house == 7 and mars_house == 7:
        indicators.append("Both Saturn and Mars in 7th house → very difficult marital life; divorce risk")

    # D9: malefics in 7th confirm difficulty
    malefics_7th_d9 = [p for p in _planets_in_house(7, d9) if p in NATURAL_MALEFICS]
    if len(malefics_7th_d9) >= 2:
        indicators.append(
            f"Multiple malefics {malefics_7th_d9} in D9's 7th → confirmed marital difficulties across lives"
        )

    # Dasha periods that bring divorce
    divorce_dashas = []
    ul_2nd_lord = SIGN_LORD[ul_2nd]
    ul_7th_lord = SIGN_LORD[ul_7th]
    lagna_6th_sign = _sign_of_house(lagna_sign, 6)
    lagna_8th_sign = _sign_of_house(lagna_sign, 8)
    lagna_6th_lord = SIGN_LORD[lagna_6th_sign]
    lagna_8th_lord = SIGN_LORD[lagna_8th_sign]

    for planet_name in {ul_2nd_lord, ul_7th_lord, lagna_6th_lord, lagna_8th_lord}:
        role = []
        if planet_name == ul_2nd_lord:
            role.append(f"lord of 2nd from UL ({ul_2nd})")
        if planet_name == ul_7th_lord:
            role.append(f"lord of 7th from UL ({ul_7th})")
        if planet_name == lagna_6th_lord:
            role.append(f"lord of 6th from lagna")
        if planet_name == lagna_8th_lord:
            role.append(f"lord of 8th from lagna")
        divorce_dashas.append({
            "planet": planet_name,
            "roles": role,
            "note": "Dasha / Antardasha of this planet can bring marital troubles or separation",
        })

    severity = "None"
    if len(indicators) >= 3:
        severity = "High"
    elif len(indicators) >= 2:
        severity = "Moderate"
    elif indicators:
        severity = "Low"

    return {
        "severity": severity,
        "indicators": indicators,
        "divorce_dasha_planets": divorce_dashas,
        "ul_2nd_from": ul_2nd,
        "ul_7th_from": ul_7th,
        "description": (
            "Divorce/separation is indicated by malefics in the 2nd and 7th from UL "
            "(these are the 'end-of-marriage' positions). "
            "The 6th and 8th houses from lagna bring marital troubles and quarrels. "
            "D9's 7th with malefics confirms difficulties across the dharmic dimension. "
            "Dashas of the lords of 2nd/7th from UL and 6th/8th from lagna are trigger periods."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. Marriage Quality Summary
# ─────────────────────────────────────────────────────────────────────────────

def _marriage_quality_score(
        upapada: dict, seventh_house: dict, dk_analysis: dict, delay: dict, divorce: dict
) -> dict:
    """
    Produce an overall marriage quality assessment.
    """
    positive = []
    negative = []

    # UL lord strength
    if upapada["ul_lord_strength"] in ("exalted", "own sign"):
        positive.append(f"UL lord ({upapada['ul_lord']}) is {upapada['ul_lord_strength']} — strong marriage foundation")
    elif upapada["ul_lord_strength"] == "debilitated":
        negative.append(f"UL lord ({upapada['ul_lord']}) debilitated — challenges in marriage")

    # 7th lord D1 strength
    s7 = seventh_house["d1"]
    if s7["7th_lord_strength"] in ("exalted", "own sign"):
        positive.append(f"7th lord ({s7['7th_lord']}) is {s7['7th_lord_strength']} — excellent partner potential")
    elif s7["7th_lord_strength"] == "debilitated":
        negative.append(f"7th lord ({s7['7th_lord']}) debilitated — partner may face struggles")

    # Venus strength
    v = seventh_house["venus"]
    if v["strength"] in ("exalted", "own sign"):
        positive.append(f"Venus is {v['strength']} — beautiful, loving relationship")
    elif v["strength"] == "debilitated":
        negative.append("Venus debilitated (Virgo) — difficulties in love life")

    # D9 7th house
    for note in seventh_house["d9"]["notes"]:
        if "auspicious" in note or "supportive" in note or "noble" in note:
            positive.append(note)
        else:
            negative.append(note)

    # DK strength
    if dk_analysis.get("strength") in ("exalted", "own sign"):
        positive.append(
            f"DK ({dk_analysis['dara_karaka_planet']}) is {dk_analysis['strength']} — strong, admirable spouse")
    elif dk_analysis.get("strength") == "debilitated":
        negative.append(f"DK ({dk_analysis['dara_karaka_planet']}) debilitated — spouse may struggle")

    # Marriage longevity
    for note in upapada["marriage_longevity"]["notes"]:
        if "long" in note or "stable" in note:
            positive.append(note)
        else:
            negative.append(note)

    # Delay
    if delay["severity"] not in ("None",):
        negative.append(f"Marriage delay/challenge: {delay['severity']}")

    # Divorce
    if divorce["severity"] not in ("None",):
        negative.append(f"Divorce/separation risk: {divorce['severity']}")

    # Score
    score = len(positive) - len(negative)
    if score >= 3:
        overall = "Excellent marriage prospects — happy, stable, and loving union likely"
    elif score >= 1:
        overall = "Good marriage prospects with some challenges to navigate"
    elif score == 0:
        overall = "Mixed marriage prospects — requires careful timing and effort"
    else:
        overall = "Challenging marriage prospects — remedies and careful partner selection advised"

    return {
        "overall_verdict": overall,
        "positive_factors": positive,
        "negative_factors": negative,
        "quality_score": score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def predict_marriage(final_structure: dict[str, Any]) -> dict:
    """
    Main entry point — pass the dict returned by generate_kundli().
    Returns comprehensive marriage prediction covering:
      - Upapada Lagna (UL)
      - Dara Karaka (DK)
      - 7th house (D1 + D9)
      - Darapada (A7)
      - Delay / denial indicators
      - Multiple marriages risk
      - Dasha-based timing
      - Transit triggers
      - Divorce indicators
      - Overall quality summary
    """
    planets_data = final_structure.get("planets_data", [])
    house_mapper = final_structure.get("house_mapper", {})
    d1 = house_mapper.get("D1", {})
    d9 = house_mapper.get("D9", {})
    all_dashas = final_structure.get("dasha", {}).get("all_mahadashas", [])

    lagna = _lagna_sign(planets_data)
    if not lagna:
        return {"error": "Ascendant not found in planets_data"}

    # Core analyses
    upapada = analyze_upapada(lagna, planets_data, d1)
    dk_result = analyze_dara_karaka(planets_data, d1, d9)
    seventh = analyze_7th_house(lagna, planets_data, d1, d9)
    darapada = analyze_darapada(lagna, planets_data, upapada["ul_sign"])
    delay = analyze_marriage_delay(lagna, planets_data, d1, d9)
    multiple = analyze_multiple_marriages(lagna, planets_data, d1, upapada["ul_sign"])
    timing = analyze_marriage_timing_dasha(lagna, planets_data, d1, d9, upapada["ul_sign"], all_dashas)
    transits = analyze_marriage_transit_triggers(lagna, planets_data, d1)
    divorce = analyze_divorce_indicators(lagna, planets_data, d1, d9, upapada["ul_sign"])
    quality = _marriage_quality_score(upapada, seventh, dk_result, delay, divorce)

    return {
        "lagna": lagna,
        "upapada_lagna": upapada,
        "dara_karaka": dk_result,
        "seventh_house_analysis": seventh,
        "darapada_a7": darapada,
        "delay_denial": delay,
        "multiple_marriages": multiple,
        "marriage_timing_dasha": timing,
        "transit_triggers": transits,
        "divorce_indicators": divorce,
        "overall_quality": quality,
    }
