"""
dosha_calculator.py
-------------------
Calculates major Vedic astrology doshas from kundli data.

Primary source : D1 (Rashi) chart — planets_data + house_mapper["D1"]
Supporting     : D9 (Navamsa) chart — house_mapper["D9"]  (cancellation checks)

Usage:
    from dosha_calculator import calculate_doshas
    result = calculate_doshas(final_structure)   # pass the dict returned by generate_kundli()
"""
from __future__ import annotations

from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _planet_map(planets_data: list[dict]) -> dict[str, dict]:
    """Return {planet_name: planet_dict} for quick lookups."""
    return {p["name"]: p for p in planets_data}


def _house_of(planet_name: str, d1: dict[str, list]) -> int | None:
    """Return the D1 house number (1-12) that contains the given planet."""
    for house_num, occupants in d1.items():
        for p in occupants:
            if p["name"] == planet_name:
                return int(house_num)
    return None


def _planets_in_house(house_num: int, chart: dict[str, list]) -> list[str]:
    """Return list of planet names present in a given house."""
    return [p["name"] for p in chart.get(str(house_num), [])]


def _are_conjunct(p1: str, p2: str, d1: dict) -> bool:
    """True if both planets occupy the same D1 house."""
    h1 = _house_of(p1, d1)
    h2 = _house_of(p2, d1)
    return h1 is not None and h1 == h2


def _longitude_diff(lon1: float, lon2: float) -> float:
    """Smallest angular difference between two ecliptic longitudes (0-180)."""
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Mangal Dosha  (also called Kuja Dosha / Manglik Dosha)
# ──────────────────────────────────────────────────────────────────────────────

MANGAL_DOSHA_HOUSES = {1, 2, 4, 7, 8, 12}

# Classic cancellation conditions (D1-based)
MANGAL_CANCEL_SIGNS_FOR_MARS = {"Aries", "Scorpio"}  # own signs
MANGAL_CANCEL_SIGNS_LAGNA = {"Aries", "Scorpio", "Cancer",
                             "Capricorn", "Leo", "Sagittarius"}


def check_mangal_dosha(planets_data: list, d1: dict, d9: dict) -> dict:
    """
    Mangal Dosha: Mars in houses 1,2,4,7,8,12 counted from
    Lagna, Moon, or Venus in D1.

    Returns presence flag, affected reference points, severity,
    and cancellation details.
    """
    pm = _planet_map(planets_data)

    mars_house_from_lagna = _house_of("Mars", d1)
    moon_house = _house_of("Moon", d1)
    venus_house = _house_of("Venus", d1)
    mars_zodiac = pm["Mars"]["zodiac"] if "Mars" in pm else None

    # Relative house of Mars from Moon and Venus
    def relative_house(reference_house: int | None) -> int | None:
        if reference_house is None or mars_house_from_lagna is None:
            return None
        return ((mars_house_from_lagna - reference_house) % 12) + 1

    affected_from = []

    if mars_house_from_lagna in MANGAL_DOSHA_HOUSES:
        affected_from.append("Lagna")

    rel_moon = relative_house(moon_house)
    if rel_moon in MANGAL_DOSHA_HOUSES:
        affected_from.append("Moon")

    rel_venus = relative_house(venus_house)
    if rel_venus in MANGAL_DOSHA_HOUSES:
        affected_from.append("Venus")

    present = bool(affected_from)

    # ── Cancellation checks ──────────────────────────────────────────────────
    cancellations = []

    if present and mars_zodiac:
        # 1. Mars in own sign (Aries / Scorpio) — strong cancellation
        if mars_zodiac in MANGAL_CANCEL_SIGNS_FOR_MARS:
            cancellations.append("Mars is in its own sign — Mangal Dosha cancelled")

        # 2. Mars in 2nd house but no malefic in 8th — partial
        if mars_house_from_lagna == 2:
            planets_in_8 = _planets_in_house(8, d1)
            malefics_in_8 = [p for p in planets_in_8 if p in ("Saturn", "Rahu", "Ketu")]
            if not malefics_in_8:
                cancellations.append("Mars in 2nd with no malefic in 8th — partial cancellation")

        # 3. Mars in Lagna and Lagna sign is Aries/Scorpio/Cancer/Capricorn
        lagna_sign = next(
            (p["zodiac"] for p in planets_data if p["name"] == "Ascendant"), None
        )
        if mars_house_from_lagna == 1 and lagna_sign in MANGAL_CANCEL_SIGNS_LAGNA:
            cancellations.append(f"Mars in 1st house in {lagna_sign} Lagna — Mangal Dosha cancelled")

        # 4. Jupiter aspecting Mars (Jupiter aspects 5th, 7th, 9th from itself)
        jupiter_house = _house_of("Jupiter", d1)
        if jupiter_house and mars_house_from_lagna:
            jupiter_aspects = {
                (jupiter_house + 4) % 12 + 1,
                (jupiter_house + 6) % 12 + 1,
                (jupiter_house + 8) % 12 + 1,
            }
            if mars_house_from_lagna in jupiter_aspects:
                cancellations.append("Jupiter aspects Mars — Mangal Dosha significantly reduced")

        # 5. D9 check: Mars well-placed in D9 (own sign or exalted)
        mars_d9_sign = None
        for h, occupants in d9.items():
            for p in occupants:
                if p["name"] == "Mars":
                    mars_d9_sign = p["sign"]
        if mars_d9_sign in ("Aries", "Scorpio", "Capricorn"):  # own / exalted
            cancellations.append(f"Mars in {mars_d9_sign} in D9 (Navamsa) — Mangal Dosha cancelled/reduced")

    # Severity
    if not present:
        severity = "None"
    elif len(affected_from) == 3:
        severity = "High"
    elif len(affected_from) == 2:
        severity = "Moderate"
    else:
        severity = "Low"

    if cancellations:
        severity = severity + " (with cancellation)"

    return {
        "present": str(present),
        "affected_from": affected_from,
        "mars_house_d1": mars_house_from_lagna,
        "mars_sign_d1": mars_zodiac,
        "severity": str(severity),
        "cancellations": cancellations,
        "description": (
            'Mangal Dosha occurs when Mars is placed in houses 1-2-4-7-8-12'
            'counted from Lagna; Moon; or Venus. It can affect marriage and relationships.'
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. Kaal Sarp Dosha
# ──────────────────────────────────────────────────────────────────────────────

PLANET_ORDER = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]


def check_kaal_sarp_dosha(planets_data: list) -> dict:
    """
    Kaal Sarp Dosha: All 7 classic planets (Sun–Saturn) fall within
    the arc from Rahu to Ketu (going in the direction of zodiac).

    Returns type (Anuloma / Viloma), name of the dosha, and severity.
    """
    pm = _planet_map(planets_data)

    rahu_lon = pm["Rahu"]["longitude"]
    ketu_lon = pm["Ketu"]["longitude"]

    def in_rahu_ketu_arc(lon: float, start: float, end: float) -> bool:
        """Is lon within the arc from start to end (going forward)?"""
        if start < end:
            return start < lon < end
        else:  # arc wraps around 0°
            return lon > start or lon < end

    all_in_rahu_to_ketu = all(
        in_rahu_ketu_arc(pm[p]["longitude"], rahu_lon, ketu_lon)
        for p in PLANET_ORDER if p in pm
    )
    all_in_ketu_to_rahu = all(
        in_rahu_ketu_arc(pm[p]["longitude"], ketu_lon, rahu_lon)
        for p in PLANET_ORDER if p in pm
    )

    present = all_in_rahu_to_ketu or all_in_ketu_to_rahu

    # Name the specific Kaal Sarp type based on Rahu's house
    pm_list = planets_data
    rahu_sign_index = next(
        (i for i, p in enumerate(pm_list) if p["name"] == "Rahu"), None
    )

    KAAL_SARP_NAMES = [
        "Anant", "Kulik", "Vasuki", "Shankhpal", "Padma", "Mahapadma",
        "Takshak", "Karkotak", "Shankhnaad", "Patak", "Vishakta", "Sheshnag"
    ]

    dosha_name = None
    dosha_type = None
    if present:
        rahu_zodiac = pm["Rahu"]["zodiac"]
        from utils.config import signs
        rahu_house_approx = signs.index(rahu_zodiac) if rahu_zodiac in signs else 0
        dosha_name = KAAL_SARP_NAMES[rahu_house_approx % 12]
        dosha_type = "Anuloma (Rahu→Ketu)" if all_in_rahu_to_ketu else "Viloma (Ketu→Rahu)"

    # Check partial (some planets outside arc)
    planets_outside = [
        p for p in PLANET_ORDER
        if p in pm and not (
                in_rahu_ketu_arc(pm[p]["longitude"], rahu_lon, ketu_lon) or
                in_rahu_ketu_arc(pm[p]["longitude"], ketu_lon, rahu_lon)
        )
    ]

    return {
        "present": str(present),
        "dosha_name": str(dosha_name),
        "dosha_type": str(dosha_type),
        "rahu_longitude": round(rahu_lon, 4),
        "ketu_longitude": round(ketu_lon, 4),
        "planets_outside_arc": planets_outside if not present else [],
        "description": (
            "Kaal Sarp Dosha occurs when all 7 planets are hemmed between Rahu and Ketu. "
            'It can cause obstacles; delays; and karmic challenges in life.'
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. Pitra Dosha
# ──────────────────────────────────────────────────────────────────────────────

def check_pitra_dosha(planets_data: list, d1: dict) -> dict:
    """
    Pitra Dosha: Caused by affliction to Sun (karaka for father/ancestors).

    Primary triggers:
    - Sun conjunct Rahu or Ketu in D1
    - Sun in 9th house afflicted by Saturn, Rahu, or Ketu
    - Rahu in 9th or 10th house
    - Moon + Rahu conjunction (Chandra Grahan yoga — secondary)
    """
    pm = _planet_map(planets_data)

    sun_house = _house_of("Sun", d1)
    rahu_house = _house_of("Rahu", d1)
    ketu_house = _house_of("Ketu", d1)
    moon_house = _house_of("Moon", d1)
    saturn_house = _house_of("Saturn", d1)

    triggers = []

    # 1. Sun conjunct Rahu (within same house)
    if _are_conjunct("Sun", "Rahu", d1):
        lon_diff = _longitude_diff(pm["Sun"]["longitude"], pm["Rahu"]["longitude"])
        if lon_diff <= 15:
            triggers.append("Sun closely conjunct Rahu (within 15°) — strong Pitra Dosha")
        else:
            triggers.append("Sun in same house as Rahu — Pitra Dosha present")

    # 2. Sun conjunct Ketu
    if _are_conjunct("Sun", "Ketu", d1):
        triggers.append("Sun conjunct Ketu — Pitra Dosha present")

    # 3. Sun in 9th house with Saturn / Rahu / Ketu
    if sun_house == 9:
        planets_9 = _planets_in_house(9, d1)
        afflictors = [p for p in planets_9 if p in ("Saturn", "Rahu", "Ketu")]
        if afflictors:
            triggers.append(f"Sun in 9th house with {', '.join(afflictors)} — Pitra Dosha")

    # 4. Rahu in 9th or 10th house
    if rahu_house in (9, 10):
        triggers.append(f"Rahu in {rahu_house}th house — Pitra Dosha indicator")

    # 5. Saturn aspecting Sun (Saturn aspects 3rd, 7th, 10th from itself)
    if saturn_house and sun_house:
        saturn_aspects = {
            (saturn_house + 2) % 12 + 1,
            (saturn_house + 6) % 12 + 1,
            (saturn_house + 9) % 12 + 1,
        }
        if sun_house in saturn_aspects:
            triggers.append("Saturn aspects Sun — additional Pitra Dosha influence")

    present = bool(triggers)
    severity = "High" if len(triggers) >= 3 else "Moderate" if len(triggers) == 2 else "Low" if triggers else "None"

    return {
        "present": str(present),
        "severity": str(severity),
        "triggers": triggers,
        "sun_house": sun_house,
        "rahu_house": rahu_house,
        "description": (
            "Pitra Dosha indicates karmic debt to ancestors. It can cause obstacles in "
            "progeny, career, and family harmony. Remedies include Pitru Tarpan and charity."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. Guru Chandal Dosha
# ──────────────────────────────────────────────────────────────────────────────

def check_guru_chandal_dosha(planets_data: list, d1: dict) -> dict:
    """
    Guru Chandal Dosha: Jupiter conjunct or aspected by Rahu or Ketu in D1.

    - Conjunction (same house) = strong dosha
    - Rahu/Ketu in 5th, 7th, 9th from Jupiter = aspect dosha
    """
    pm = _planet_map(planets_data)

    jupiter_house = _house_of("Jupiter", d1)
    rahu_house = _house_of("Rahu", d1)
    ketu_house = _house_of("Ketu", d1)

    triggers = []
    dosha_type = None

    # 1. Jupiter conjunct Rahu
    if _are_conjunct("Jupiter", "Rahu", d1):
        lon_diff = _longitude_diff(pm["Jupiter"]["longitude"], pm["Rahu"]["longitude"])
        dosha_type = "Conjunction with Rahu"
        strength = "close (within 10°)" if lon_diff <= 10 else "in same house"
        triggers.append(f"Jupiter conjunct Rahu ({strength})")

    # 2. Jupiter conjunct Ketu
    if _are_conjunct("Jupiter", "Ketu", d1):
        lon_diff = _longitude_diff(pm["Jupiter"]["longitude"], pm["Ketu"]["longitude"])
        dosha_type = dosha_type or "Conjunction with Ketu"
        strength = "close (within 10°)" if lon_diff <= 10 else "in same house"
        triggers.append(f"Jupiter conjunct Ketu ({strength})")

    # 3. Rahu/Ketu aspect on Jupiter (they aspect 5th and 9th from themselves)
    if jupiter_house and rahu_house:
        rahu_aspects = {
            (rahu_house + 4) % 12 + 1,
            (rahu_house + 6) % 12 + 1,
            (rahu_house + 8) % 12 + 1,
        }
        if jupiter_house in rahu_aspects and not _are_conjunct("Jupiter", "Rahu", d1):
            triggers.append(f"Rahu aspects Jupiter from house {rahu_house}")
            dosha_type = dosha_type or "Aspect from Rahu"

    if jupiter_house and ketu_house:
        ketu_aspects = {
            (ketu_house + 4) % 12 + 1,
            (ketu_house + 6) % 12 + 1,
            (ketu_house + 8) % 12 + 1,
        }
        if jupiter_house in ketu_aspects and not _are_conjunct("Jupiter", "Ketu", d1):
            triggers.append(f"Ketu aspects Jupiter from house {ketu_house}")
            dosha_type = dosha_type or "Aspect from Ketu"

    present = bool(triggers)
    severity = "High" if len(triggers) >= 2 else "Moderate" if triggers else "None"

    return {
        "present": str(present),
        "dosha_type": str(dosha_type),
        "severity": str(severity),
        "triggers": triggers,
        "jupiter_house": jupiter_house,
        "rahu_house": rahu_house,
        "ketu_house": ketu_house,
        "description": (
            "Guru Chandal Dosha afflicts Jupiter (wisdom; dharma; teachers) by Rahu/Ketu. "
            "It can lead to misguided decisions; issues with gurus; and ethical dilemmas."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. Grahan Dosha  (Solar / Lunar Eclipse Dosha)
# ──────────────────────────────────────────────────────────────────────────────

def check_grahan_dosha(planets_data: list, d1: dict, d9: dict) -> dict:
    """
    Grahan Dosha:
    - Surya Grahan: Sun conjunct Rahu or Ketu
    - Chandra Grahan: Moon conjunct Rahu or Ketu

    D9 is used to check if the affliction persists (severity confirmation).
    """
    pm = _planet_map(planets_data)

    triggers = []
    grahan_types = []

    # Surya Grahan
    if _are_conjunct("Sun", "Rahu", d1):
        diff = _longitude_diff(pm["Sun"]["longitude"], pm["Rahu"]["longitude"])
        triggers.append(f"Sun conjunct Rahu in D1 (separation: {round(diff, 2)}°)")
        grahan_types.append("Surya Grahan (Solar)")

    if _are_conjunct("Sun", "Ketu", d1):
        diff = _longitude_diff(pm["Sun"]["longitude"], pm["Ketu"]["longitude"])
        triggers.append(f"Sun conjunct Ketu in D1 (separation: {round(diff, 2)}°)")
        grahan_types.append("Surya Grahan (Solar)")

    # Chandra Grahan
    if _are_conjunct("Moon", "Rahu", d1):
        diff = _longitude_diff(pm["Moon"]["longitude"], pm["Rahu"]["longitude"])
        triggers.append(f"Moon conjunct Rahu in D1 — Chandra Grahan (separation: {round(diff, 2)}°)")
        grahan_types.append("Chandra Grahan (Lunar)")

    if _are_conjunct("Moon", "Ketu", d1):
        diff = _longitude_diff(pm["Moon"]["longitude"], pm["Ketu"]["longitude"])
        triggers.append(f"Moon conjunct Ketu in D1 — Chandra Grahan (separation: {round(diff, 2)}°)")
        grahan_types.append("Chandra Grahan (Lunar)")

    present = bool(triggers)

    # D9 confirmation — does the same conjunction persist in Navamsa?
    d9_confirmation = []
    if present:
        if _are_conjunct("Sun", "Rahu", d9) or _are_conjunct("Sun", "Ketu", d9):
            d9_confirmation.append("Sun-node conjunction confirmed in D9 — stronger Surya Grahan Dosha")
        if _are_conjunct("Moon", "Rahu", d9) or _are_conjunct("Moon", "Ketu", d9):
            d9_confirmation.append("Moon-node conjunction confirmed in D9 — stronger Chandra Grahan Dosha")

    severity = "None"
    if present:
        if d9_confirmation:
            severity = "High"
        elif len(triggers) >= 2:
            severity = "Moderate"
        else:
            severity = "Low"

    return {
        "present": str(present),
        "grahan_types": list(set(grahan_types)),
        "severity": str(severity),
        "triggers": triggers,
        "d9_confirmation": d9_confirmation,
        "description": (
            "Grahan Dosha occurs when Sun or Moon is conjunct Rahu/Ketu. "
            "It can affect health, confidence (Sun), and mental peace (Moon)."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. Shani Dosha  (Saturn affliction — natal, not transit Sade Sati)
# ──────────────────────────────────────────────────────────────────────────────

SATURN_AFFLICTION_HOUSES = {1, 4, 7, 8, 12}


def check_shani_dosha(planets_data: list, d1: dict) -> dict:
    """
    Natal Shani Dosha:
    - Saturn in houses 1, 4, 7, 8, 12
    - Saturn conjunct or aspecting Moon / Lagna lord
    - Saturn conjunct Rahu (Shani-Rahu Shrapit Dosha)
    """
    pm = _planet_map(planets_data)

    saturn_house = _house_of("Saturn", d1)
    moon_house = _house_of("Moon", d1)
    saturn_zodiac = pm.get("Saturn", {}).get("zodiac")

    triggers = []

    # 1. Saturn in difficult houses
    if saturn_house in SATURN_AFFLICTION_HOUSES:
        triggers.append(f"Saturn in house {saturn_house} — Shani Dosha")

    # 2. Saturn + Rahu conjunction (Shrapit Dosha)
    if _are_conjunct("Saturn", "Rahu", d1):
        triggers.append("Saturn conjunct Rahu — Shrapit/Shani Dosha")

    # 3. Saturn aspects Moon (3rd, 7th, 10th aspect)
    if saturn_house and moon_house:
        saturn_aspects = {
            (saturn_house + 2) % 12 + 1,
            (saturn_house + 6) % 12 + 1,
            (saturn_house + 9) % 12 + 1,
        }
        if moon_house in saturn_aspects:
            triggers.append(f"Saturn aspects Moon from house {saturn_house} — mental pressure")

    # 4. Saturn in debilitation (Aries) in a malefic house
    if saturn_zodiac == "Aries" and saturn_house in SATURN_AFFLICTION_HOUSES:
        triggers.append("Saturn debilitated (Aries) in a malefic house — intensified Shani Dosha")

    # Cancellation: Saturn in own sign (Capricorn/Aquarius) or exalted (Libra)
    cancellations = []
    if saturn_zodiac in ("Capricorn", "Aquarius"):
        cancellations.append(f"Saturn in own sign ({saturn_zodiac}) — Shani Dosha reduced")
    elif saturn_zodiac == "Libra":
        cancellations.append("Saturn exalted (Libra) — Shani Dosha significantly reduced")

    present = bool(triggers)
    severity = "High" if len(triggers) >= 3 else "Moderate" if len(triggers) == 2 else "Low" if triggers else "None"
    if cancellations and present:
        severity += " (with cancellation)"

    return {
        "present": str(present),
        "severity": str(severity),
        "triggers": triggers,
        "cancellations": cancellations,
        "saturn_house": saturn_house,
        "saturn_sign": saturn_zodiac,
        "description": (
            'Shani Dosha (natal) denotes Saturn;s challenging placement. '
            'It can cause delays, hardships, and karmic lessons in the affected houses.'
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# Master function
# ──────────────────────────────────────────────────────────────────────────────

def calculate_doshas(final_structure: dict[str, Any]) -> dict:
    """
    Main entry point.
    Pass the dict returned by generate_kundli().

    Returns a 'doshas' dict with results for each dosha.
    """
    planets_data = final_structure.get("planets_data", [])
    house_mapper = final_structure.get("house_mapper", {})

    d1 = house_mapper.get("D1", {})
    d9 = house_mapper.get("D9", {})

    return {
        "mangal_dosha": check_mangal_dosha(planets_data, d1, d9),
        "kaal_sarp_dosha": check_kaal_sarp_dosha(planets_data),
        "pitra_dosha": check_pitra_dosha(planets_data, d1),
        "guru_chandal_dosha": check_guru_chandal_dosha(planets_data, d1),
        "grahan_dosha": check_grahan_dosha(planets_data, d1, d9),
        "shani_dosha": check_shani_dosha(planets_data, d1),
    }
