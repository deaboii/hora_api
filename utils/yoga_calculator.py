"""
yoga_calculator.py
------------------
Calculates major Vedic astrology Yogas from D1 (Rashi) chart data.

Yogas implemented:
    1. Panch Mahapurusha Yogas  (Ruchaka, Bhadra, Hamsa, Malavya, Shasha)
    2. Raj Yoga
    3. Dhana Yoga
    4. Gaja Kesari Yoga + Kemdrum Yoga  (Moon-based)
    5. Viparita Raja Yoga

Usage:
    from yoga_calculator import calculate_yogas
    result = calculate_yogas(final_structure)   # dict returned by generate_kundli()
"""
from __future__ import annotations

from utils.config import signs

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

KENDRA_HOUSES  = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}
DUSTHANA_HOUSES = {6, 8, 12}

SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

# Exalted signs for each planet
EXALTED_SIGN = {
    "Sun":     "Aries",
    "Moon":    "Taurus",
    "Mars":    "Capricorn",
    "Mercury": "Virgo",
    "Jupiter": "Cancer",
    "Venus":   "Pisces",
    "Saturn":  "Libra",
}

# Own signs for each planet
OWN_SIGNS = {
    "Sun":     {"Leo"},
    "Moon":    {"Cancer"},
    "Mars":    {"Aries", "Scorpio"},
    "Mercury": {"Gemini", "Virgo"},
    "Jupiter": {"Sagittarius", "Pisces"},
    "Venus":   {"Taurus", "Libra"},
    "Saturn":  {"Capricorn", "Aquarius"},
}

# Lagna lord for each sign (sign -> ruling planet)
SIGN_LORD = {
    "Aries":       "Mars",
    "Taurus":      "Venus",
    "Gemini":      "Mercury",
    "Cancer":      "Moon",
    "Leo":         "Sun",
    "Virgo":       "Mercury",
    "Libra":       "Venus",
    "Scorpio":     "Mars",
    "Sagittarius": "Jupiter",
    "Capricorn":   "Saturn",
    "Aquarius":    "Saturn",
    "Pisces":      "Jupiter",
}

# Panch Mahapurusha planets and their yoga names
PANCH_MAHAPURUSHA = {
    "Mars":    "Ruchaka Yoga",
    "Mercury": "Bhadra Yoga",
    "Jupiter": "Hamsa Yoga",
    "Venus":   "Malavya Yoga",
    "Saturn":  "Shasha Yoga",
}

PANCH_DESCRIPTIONS = {
    "Ruchaka Yoga": "Formed by Mars. Gives courage, leadership, physical strength, and military/athletic success.",
    "Bhadra Yoga":  "Formed by Mercury. Gives sharp intellect, excellent communication, business acumen.",
    "Hamsa Yoga":   "Formed by Jupiter. Gives wisdom, spirituality, good fortune, and respected status.",
    "Malavya Yoga": "Formed by Venus. Gives beauty, luxury, artistic talent, and marital happiness.",
    "Shasha Yoga":  "Formed by Saturn. Gives authority, discipline, longevity, and leadership over masses.",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _planet_map(planets_data: list) -> dict:
    """Return {planet_name: planet_dict}."""
    return {p["name"]: p for p in planets_data}


def _house_of(planet_name: str, d1: dict) -> int | None:
    """Return house number (1-12) of a planet in D1."""
    for house_num, occupants in d1.items():
        for p in occupants:
            if p["name"] == planet_name:
                return int(house_num)
    return None


def _planets_in_house(house_num: int, d1: dict) -> list[str]:
    """Return planet names in a given house."""
    return [p["name"] for p in d1.get(str(house_num), [])]


def _sign_of_house(lagna_sign: str, house_num: int) -> str:
    """Return the zodiac sign of a given house number from lagna."""
    lagna_index = SIGN_INDEX[lagna_sign]
    return signs[(lagna_index + house_num - 1) % 12]


def _lord_of_house(lagna_sign: str, house_num: int) -> str:
    """Return the ruling planet of a given house."""
    house_sign = _sign_of_house(lagna_sign, house_num)
    return SIGN_LORD[house_sign]


def _are_conjunct(p1: str, p2: str, d1: dict) -> bool:
    """True if both planets are in the same house."""
    h1 = _house_of(p1, d1)
    h2 = _house_of(p2, d1)
    return h1 is not None and h1 == h2


def _get_lagna_sign(planets_data: list) -> str | None:
    """Return the Ascendant sign."""
    for p in planets_data:
        if p["name"] == "Ascendant":
            return p["zodiac"]
    return None


def _aspects_house(from_house: int, target_house: int, planet: str = None) -> bool:
    """
    Check if a planet in from_house aspects target_house.
    Uses 7th house aspect (all planets) + special aspects for Mars/Jupiter/Saturn.
    """
    # 7th aspect — all planets
    if (from_house + 6) % 12 + 1 == target_house:
        return True
    # Special aspects
    if planet == "Mars":
        if (from_house + 3) % 12 + 1 == target_house:  # 4th
            return True
        if (from_house + 7) % 12 + 1 == target_house:  # 8th
            return True
    if planet == "Jupiter":
        if (from_house + 4) % 12 + 1 == target_house:  # 5th
            return True
        if (from_house + 8) % 12 + 1 == target_house:  # 9th
            return True
    if planet == "Saturn":
        if (from_house + 2) % 12 + 1 == target_house:  # 3rd
            return True
        if (from_house + 9) % 12 + 1 == target_house:  # 10th
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# 1. Panch Mahapurusha Yogas
# ──────────────────────────────────────────────────────────────────────────────

def check_panch_mahapurusha(planets_data: list, d1: dict) -> dict:
    """
    Condition: Planet (Mars/Mercury/Jupiter/Venus/Saturn) must be:
    - In its own sign OR exalted sign
    - AND placed in a Kendra house (1, 4, 7, 10)
    """
    pm = _planet_map(planets_data)
    yogas_found = []

    for planet, yoga_name in PANCH_MAHAPURUSHA.items():
        if planet not in pm:
            continue

        planet_sign  = pm[planet]["zodiac"]
        planet_house = _house_of(planet, d1)

        if planet_house is None:
            continue

        in_own_sign    = planet_sign in OWN_SIGNS.get(planet, set())
        is_exalted     = planet_sign == EXALTED_SIGN.get(planet)
        in_kendra      = planet_house in KENDRA_HOUSES

        if (in_own_sign or is_exalted) and in_kendra:
            yogas_found.append({
                "yoga": yoga_name,
                "planet": planet,
                "house": planet_house,
                "sign": planet_sign,
                "strength": "Exalted" if is_exalted else "Own Sign",
                "present": True,
                "description": PANCH_DESCRIPTIONS[yoga_name]
            })

    return {
        "present": str(bool(yogas_found)),
        "count": len(yogas_found),
        "yogas": str(yogas_found),
        "description": (
            "Panch Mahapurusha Yogas are formed when Mars; Mercury; Jupiter; Venus; or Saturn "
            "are in their own/exalted sign AND in a Kendra (1;4;7;10) house. "
            "These are among the most powerful yogas in Vedic astrology."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. Raj Yoga
# ──────────────────────────────────────────────────────────────────────────────

def check_raj_yoga(planets_data: list, d1: dict) -> dict:
    """
    Raj Yoga: Lord of a Kendra house (1,4,7,10) conjuncts or mutually aspects
    the lord of a Trikona house (1,5,9) in D1.

    House 1 counts as both Kendra and Trikona — handled carefully.
    """
    lagna_sign = _get_lagna_sign(planets_data)
    if not lagna_sign:
        return {"present": False, "yogas": [], "description": ""}

    yogas_found = []

    kendra_lords  = {h: _lord_of_house(lagna_sign, h) for h in KENDRA_HOUSES}
    trikona_lords = {h: _lord_of_house(lagna_sign, h) for h in TRIKONA_HOUSES}

    checked_pairs = set()

    for kh, kl in kendra_lords.items():
        for th, tl in trikona_lords.items():
            # Skip same house (1st is both kendra and trikona)
            if kh == th:
                continue
            # Skip duplicate planet pairs
            pair_key = tuple(sorted([kl, tl]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            kl_house = _house_of(kl, d1)
            tl_house = _house_of(tl, d1)

            if kl_house is None or tl_house is None:
                continue

            # Conjunction
            if kl_house == tl_house:
                yogas_found.append({
                    "yoga": "Raj Yoga",
                    "type": "Conjunction",
                    "kendra_lord": f"{kl} (lord of {kh}th)",
                    "trikona_lord": f"{tl} (lord of {th}th)",
                    "house": kl_house,
                    "description": f"{kl} (Kendra lord) conjunct {tl} (Trikona lord) in house {kl_house}"
                })
            # Mutual aspect (7th from each other)
            elif (kl_house + 6) % 12 + 1 == tl_house or (tl_house + 6) % 12 + 1 == kl_house:
                yogas_found.append({
                    "yoga": "Raj Yoga",
                    "type": "Mutual Aspect",
                    "kendra_lord": f"{kl} (lord of {kh}th)",
                    "trikona_lord": f"{tl} (lord of {th}th)",
                    "kendra_lord_house": kl_house,
                    "trikona_lord_house": tl_house,
                    "description": f"{kl} (Kendra lord; house {kl_house}) mutually aspects {tl} (Trikona lord; house {tl_house})"
                })
            # Sign exchange (Parivartana)
            elif (
                pm := _planet_map(planets_data),
                kl in pm and tl in pm and
                pm[kl]["zodiac"] == _sign_of_house(lagna_sign, th) and
                pm[tl]["zodiac"] == _sign_of_house(lagna_sign, kh)
            )[-1]:
                yogas_found.append({
                    "yoga": "Raj Yoga (Parivartana)",
                    "type": "Sign Exchange",
                    "kendra_lord": f"{kl} (lord of {kh}th)",
                    "trikona_lord": f"{tl} (lord of {th}th)",
                    "description": f"{kl} and {tl} are in each other's signs — Parivartana Raj Yoga"
                })

    # Strength — more combinations = stronger
    if yogas_found:
        strength = "Very Strong" if len(yogas_found) >= 3 else "Strong" if len(yogas_found) == 2 else "Present"
    else:
        strength = "Absent"

    return {
        "present": str(bool(yogas_found)),
        "count": len(yogas_found),
        "strength": strength,
        "lagna": lagna_sign,
        "yogas": str(yogas_found),
        "description": (
            "Raj Yoga is formed when lords of Kendra (1;4;7;10) and Trikona (1;5;9) houses "
            "conjunct; aspect; or exchange signs. It bestows power; authority; and success in life."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. Dhana Yoga
# ──────────────────────────────────────────────────────────────────────────────

def check_dhana_yoga(planets_data: list, d1: dict) -> dict:
    """
    Dhana Yoga (Wealth Yoga):
    - Lord of 2nd and 11th conjunct/aspect/exchange
    - Lord of 5th or 9th connected to 2nd or 11th lord
    - Jupiter in 2nd, 5th, 9th, or 11th (natural Dhana karaka)
    - Venus and Jupiter conjunction (wealth + luck)
    """
    lagna_sign = _get_lagna_sign(planets_data)
    if not lagna_sign:
        return {"present": False, "yogas": [], "description": ""}

    pm = _planet_map(planets_data)
    yogas_found = []

    lord_2  = _lord_of_house(lagna_sign, 2)
    lord_5  = _lord_of_house(lagna_sign, 5)
    lord_9  = _lord_of_house(lagna_sign, 9)
    lord_11 = _lord_of_house(lagna_sign, 11)

    h_lord2  = _house_of(lord_2,  d1)
    h_lord5  = _house_of(lord_5,  d1)
    h_lord9  = _house_of(lord_9,  d1)
    h_lord11 = _house_of(lord_11, d1)

    # 1. Lord of 2nd and 11th conjunct
    if h_lord2 and h_lord11 and h_lord2 == h_lord11 and lord_2 != lord_11:
        yogas_found.append({
            "yoga": "Dhana Yoga",
            "type": "2nd-11th Lord Conjunction",
            "planets": [lord_2, lord_11],
            "house": h_lord2,
            "description": f"Lord of 2nd ({lord_2}) and 11th ({lord_11}) conjunct in house {h_lord2}"
        })

    # 2. Lord of 2nd and 11th mutual aspect
    if h_lord2 and h_lord11 and lord_2 != lord_11:
        if (h_lord2 + 6) % 12 + 1 == h_lord11 or (h_lord11 + 6) % 12 + 1 == h_lord2:
            yogas_found.append({
                "yoga": "Dhana Yoga",
                "type": "2nd-11th Lord Mutual Aspect",
                "planets": [lord_2, lord_11],
                "description": f"Lord of 2nd ({lord_2};house {h_lord2}) and 11th ({lord_11}; house {h_lord11}) mutually aspect each other"
            })

    # 3. Lord of 5th or 9th conjunct lord of 2nd or 11th
    for luck_lord, luck_house_num in [(lord_5, 5), (lord_9, 9)]:
        h_luck = _house_of(luck_lord, d1)
        for wealth_lord, wealth_house_num in [(lord_2, 2), (lord_11, 11)]:
            if luck_lord == wealth_lord:
                continue
            h_wealth = _house_of(wealth_lord, d1)
            if h_luck and h_wealth and h_luck == h_wealth:
                yogas_found.append({
                    "yoga": "Dhana Yoga",
                    "type": f"{luck_house_num}th-{wealth_house_num}th Lord Conjunction",
                    "planets": [luck_lord, wealth_lord],
                    "house": h_luck,
                    "description": (
                        f"Lord of {luck_house_num}th ({luck_lord}) conjunct "
                        f"lord of {wealth_house_num}th ({wealth_lord}) in house {h_luck} — strong wealth yoga"
                    )
                })

    # 4. Jupiter in Dhana houses (2, 5, 9, 11)
    jupiter_house = _house_of("Jupiter", d1)
    if jupiter_house in {2, 5, 9, 11}:
        yogas_found.append({
            "yoga": "Dhana Yoga",
            "type": "Jupiter in Wealth House",
            "planet": "Jupiter",
            "house": jupiter_house,
            "description": f"Jupiter (natural wealth karaka) in house {jupiter_house} — Dhana Yoga"
        })

    # 5. Venus + Jupiter conjunction
    if _are_conjunct("Venus", "Jupiter", d1):
        yogas_found.append({
            "yoga": "Dhana Yoga",
            "type": "Venus-Jupiter Conjunction",
            "planets": ["Venus", "Jupiter"],
            "house": _house_of("Venus", d1),
            "description": "Venus and Jupiter conjunct — Lakshmi-Guru Yoga; great wealth indicator"
        })

    # 6. Lord of 2nd in 2nd or 11th (strong placement)
    if h_lord2 in {2, 11}:
        yogas_found.append({
            "yoga": "Dhana Yoga",
            "type": "2nd Lord in Wealth House",
            "planet": lord_2,
            "house": h_lord2,
            "description": f"Lord of 2nd ({lord_2}) placed in house {h_lord2} — strong wealth retention"
        })

    return {
        "present": str(bool(yogas_found)),
        "count": len(yogas_found),
        "lagna": lagna_sign,
        "yogas": str(yogas_found),
        "description": (
            "Dhana Yogas are wealth-giving combinations. "
            "They involve lords of 2nd; 5th; 9th; and 11th houses connecting with each other, "
            "indicating financial prosperity and accumulation of wealth."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. Gaja Kesari Yoga + Kemdrum Yoga  (Moon-based)
# ──────────────────────────────────────────────────────────────────────────────

def check_moon_yogas(planets_data: list, d1: dict) -> dict:
    """
    Gaja Kesari Yoga: Jupiter in Kendra (1,4,7,10) from Moon.
    Kemdrum Yoga: No planets in 2nd or 12th from Moon (isolation).
    """
    pm = _planet_map(planets_data)
    results = {}

    moon_house    = _house_of("Moon",    d1)
    jupiter_house = _house_of("Jupiter", d1)

    # ── Gaja Kesari ──────────────────────────────────────────────────────────
    gaja_kesari = {"present": False}

    if moon_house and jupiter_house:
        relative_house = ((jupiter_house - moon_house) % 12) + 1
        if relative_house in KENDRA_HOUSES:
            # Check Moon and Jupiter are not afflicted by malefics
            moon_sign    = pm.get("Moon",    {}).get("zodiac")
            jupiter_sign = pm.get("Jupiter", {}).get("zodiac")

            # Strength boost: Jupiter in own/exalted sign
            jupiter_strength = "Strong"
            if jupiter_sign in OWN_SIGNS["Jupiter"]:
                jupiter_strength = "Very Strong (Jupiter in own sign)"
            elif jupiter_sign == EXALTED_SIGN["Jupiter"]:
                jupiter_strength = "Very Strong (Jupiter exalted)"

            gaja_kesari = {
                "present": True,
                "moon_house": moon_house,
                "jupiter_house": jupiter_house,
                "jupiter_position_from_moon": f"{relative_house}th from Moon",
                "jupiter_strength": jupiter_strength,
                "description": (
                    f"Jupiter in house {jupiter_house} is in Kendra ({relative_house}th) "
                    f"from Moon in house {moon_house}. "
                    "Gaja Kesari Yoga gives wisdom;fame; good fortune; and respected status."
                )
            }

    results["gaja_kesari_yoga"] = gaja_kesari

    # ── Kemdrum Yoga ─────────────────────────────────────────────────────────
    kemdrum = {"present": False}

    if moon_house:
        house_before = (moon_house - 2) % 12 + 1   # 12th from Moon
        house_after  = moon_house % 12 + 1          # 2nd from Moon

        planets_before = _planets_in_house(house_before, d1)
        planets_after  = _planets_in_house(house_after,  d1)

        # Exclude Rahu/Ketu — they don't cancel Kemdrum
        meaningful_planets = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"}
        before_filtered = [p for p in planets_before if p in meaningful_planets]
        after_filtered  = [p for p in planets_after  if p in meaningful_planets]

        if not before_filtered and not after_filtered:
            # Check cancellations
            cancellations = []

            # 1. Moon in Kendra from Lagna
            if moon_house in KENDRA_HOUSES:
                cancellations.append("Moon in Kendra from Lagna — Kemdrum partially cancelled")

            # 2. Moon conjunct a benefic (Jupiter/Venus/Mercury)
            moon_conjuncts = _planets_in_house(moon_house, d1)
            benefics_with_moon = [p for p in moon_conjuncts if p in ("Jupiter", "Venus", "Mercury")]
            if benefics_with_moon:
                cancellations.append(f"Moon conjunct {'; '.join(benefics_with_moon)} — Kemdrum cancelled")

            # 3. Moon in own sign or exalted
            moon_sign = pm.get("Moon", {}).get("zodiac")
            if moon_sign == "Cancer":
                cancellations.append("Moon in own sign (Cancer) — Kemdrum cancelled")
            elif moon_sign == "Taurus":
                cancellations.append("Moon exalted (Taurus) — Kemdrum cancelled")

            kemdrum = {
                "present": str(not bool(cancellations)),
                "moon_house": moon_house,
                "house_before_moon": house_before,
                "house_after_moon": house_after,
                "planets_before": planets_before,
                "planets_after": planets_after,
                "cancellations": cancellations,
                "description": (
                    "Kemdrum Yoga occurs when no planets occupy the 2nd or 12th house from Moon. "
                    "It can cause loneliness; struggles; and lack of support in life."
                )
            }

    results["kemdrum_yoga"] = kemdrum

    return results


# ──────────────────────────────────────────────────────────────────────────────
# 5. Viparita Raja Yoga
# ──────────────────────────────────────────────────────────────────────────────

def check_viparita_raja_yoga(planets_data: list, d1: dict) -> dict:
    """
    Viparita Raja Yoga: Lords of Dusthana houses (6, 8, 12) placed in
    other Dusthana houses. Evil destroys evil — gives unexpected success.

    Types:
    - Harsha Yoga  : Lord of 6th in 6th, 8th, or 12th
    - Sarala Yoga  : Lord of 8th in 6th, 8th, or 12th
    - Vimala Yoga  : Lord of 12th in 6th, 8th, or 12th
    """
    lagna_sign = _get_lagna_sign(planets_data)
    if not lagna_sign:
        return {"present": False, "yogas": [], "description": ""}

    yogas_found = []

    lord_6  = _lord_of_house(lagna_sign, 6)
    lord_8  = _lord_of_house(lagna_sign, 8)
    lord_12 = _lord_of_house(lagna_sign, 12)

    h_lord6  = _house_of(lord_6,  d1)
    h_lord8  = _house_of(lord_8,  d1)
    h_lord12 = _house_of(lord_12, d1)

    # Harsha Yoga — lord of 6th in dusthana
    if h_lord6 in DUSTHANA_HOUSES:
        yogas_found.append({
            "yoga": "Harsha Yoga (Viparita Raja)",
            "type": "Lord of 6th in Dusthana",
            "planet": lord_6,
            "house": h_lord6,
            "description": (
                f"Lord of 6th ({lord_6}) placed in house {h_lord6} (Dusthana). "
                "Harsha Yoga gives victory over enemies; good health; and happiness."
            )
        })

    # Sarala Yoga — lord of 8th in dusthana
    if h_lord8 in DUSTHANA_HOUSES:
        yogas_found.append({
            "yoga": "Sarala Yoga (Viparita Raja)",
            "type": "Lord of 8th in Dusthana",
            "planet": lord_8,
            "house": h_lord8,
            "description": (
                f"Lord of 8th ({lord_8}) placed in house {h_lord8} (Dusthana). "
                "Sarala Yoga gives fearlessness; longevity; and success despite adversity."
            )
        })

    # Vimala Yoga — lord of 12th in dusthana
    if h_lord12 in DUSTHANA_HOUSES:
        yogas_found.append({
            "yoga": "Vimala Yoga (Viparita Raja)",
            "type": "Lord of 12th in Dusthana",
            "planet": lord_12,
            "house": h_lord12,
            "description": (
                f"Lord of 12th ({lord_12}) placed in house {h_lord12} (Dusthana). "
                "Vimala Yoga gives virtuous character; financial discipline; and spiritual growth."
            )
        })

    # Extra strength: if two or more Viparita lords are in same dusthana
    if len(yogas_found) >= 2:
        for y in yogas_found:
            y["strength"] = "Strong — multiple Viparita combinations present"

    return {
        "present": str(bool(yogas_found)),
        "count": len(yogas_found),
        "lagna": lagna_sign,
        "yogas": str(yogas_found),
        "description": (
            "Viparita Raja Yoga is formed when lords of Dusthana houses (6;8;12) "
            "are placed in other Dusthana houses. It gives unexpected rise; "
            "success through hardship; and ability to overcome enemies and obstacles."
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# Master function
# ──────────────────────────────────────────────────────────────────────────────

def calculate_yogas(final_structure: dict) -> dict:
    """
    Main entry point.
    Pass the dict returned by generate_kundli().

    Returns a 'yogas' dict with results for all yoga categories.
    """
    planets_data = final_structure.get("planets_data", [])
    d1 = final_structure.get("house_mapper", {}).get("D1", {})

    moon_yogas = check_moon_yogas(planets_data, d1)

    return {
        "panch_mahapurusha_yogas": check_panch_mahapurusha(planets_data, d1),
        "raj_yoga":                check_raj_yoga(planets_data, d1),
        "dhana_yoga":              check_dhana_yoga(planets_data, d1),
        "gaja_kesari_yoga":        moon_yogas["gaja_kesari_yoga"],
        "kemdrum_yoga":            moon_yogas["kemdrum_yoga"],
        "viparita_raja_yoga":      check_viparita_raja_yoga(planets_data, d1),
    }