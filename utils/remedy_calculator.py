"""
remedy_calculator.py
--------------------
Generates personalised Vedic astrology remedies and gemstone recommendations
based on:
    - Active Doshas  (from dosha_calculator.py output)
    - Weak / afflicted planets  (debilitated, in enemy sign, in dusthana)
    - Current Mahadasha / Antardasha lord  (from dasha data)
    - Lagna lord strength

Output sections:
    1. gemstones          — primary + secondary stones with wearing instructions
    2. planet_remedies    — planet-specific mantras, colours, charity, fasting
    3. dosha_remedies     — targeted remedies for each active dosha
    4. general_remedies   — universal practices (charity day, deity, etc.)

Usage:
    from remedy_calculator import calculate_remedies
    result = calculate_remedies(final_structure)   # dict from generate_kundli()
"""

from __future__ import annotations

from utils.config import signs

# ──────────────────────────────────────────────────────────────────────────────
# Reference tables
# ──────────────────────────────────────────────────────────────────────────────

SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

# Gemstone for each planet (primary / secondary)
PLANET_GEMSTONE = {
    "Sun":     {"primary": "Ruby",        "secondary": "Red Spinel / Red Garnet",   "metal": "Gold",   "finger": "Ring finger"},
    "Moon":    {"primary": "Pearl",       "secondary": "Moonstone",                 "metal": "Silver", "finger": "Little finger"},
    "Mars":    {"primary": "Red Coral",   "secondary": "Carnelian",                 "metal": "Gold/Copper", "finger": "Ring finger"},
    "Mercury": {"primary": "Emerald",     "secondary": "Green Tourmaline / Peridot","metal": "Gold",   "finger": "Little finger"},
    "Jupiter": {"primary": "Yellow Sapphire", "secondary": "Yellow Topaz / Citrine","metal": "Gold",   "finger": "Index finger"},
    "Venus":   {"primary": "Diamond",     "secondary": "White Sapphire / White Zircon", "metal": "Silver/Platinum", "finger": "Middle finger"},
    "Saturn":  {"primary": "Blue Sapphire", "secondary": "Amethyst / Blue Spinel", "metal": "Silver/Iron", "finger": "Middle finger"},
    "Rahu":    {"primary": "Hessonite (Gomed)", "secondary": "Orange Zircon",       "metal": "Silver", "finger": "Middle finger"},
    "Ketu":    {"primary": "Cat's Eye (Lehsunia)", "secondary": "Tiger's Eye",      "metal": "Silver", "finger": "Ring finger"},
}

# Best day to wear each planet's stone
PLANET_WEAR_DAY = {
    "Sun":     "Sunday",
    "Moon":    "Monday",
    "Mars":    "Tuesday",
    "Mercury": "Wednesday",
    "Jupiter": "Thursday",
    "Venus":   "Friday",
    "Saturn":  "Saturday",
    "Rahu":    "Saturday",
    "Ketu":    "Thursday",
}

# Mantra for each planet
PLANET_MANTRA = {
    "Sun":     {"seed": "Om Hraam Hreem Hraum Sah Suryaya Namah", "count": "7000 times"},
    "Moon":    {"seed": "Om Shraam Shreem Shraum Sah Chandraya Namah", "count": "11000 times"},
    "Mars":    {"seed": "Om Kraam Kreem Kraum Sah Bhaumaya Namah", "count": "10000 times"},
    "Mercury": {"seed": "Om Braam Breem Braum Sah Budhaya Namah", "count": "17000 times"},
    "Jupiter": {"seed": "Om Graam Greem Graum Sah Gurave Namah", "count": "16000 times"},
    "Venus":   {"seed": "Om Draam Dreem Draum Sah Shukraya Namah", "count": "20000 times"},
    "Saturn":  {"seed": "Om Praam Preem Praum Sah Shanaischaraya Namah", "count": "19000 times"},
    "Rahu":    {"seed": "Om Bhraam Bhreem Bhraum Sah Rahave Namah", "count": "18000 times"},
    "Ketu":    {"seed": "Om Sraam Sreem Sraum Sah Ketave Namah", "count": "7000 times"},
}

# Charity / donation for each planet
PLANET_CHARITY = {
    "Sun":     "Donate wheat, jaggery, copper, or red cloth on Sundays",
    "Moon":    "Donate rice, milk, white cloth, or silver on Mondays",
    "Mars":    "Donate red lentils (masoor dal), copper, or red cloth on Tuesdays",
    "Mercury": "Donate green moong, books, or green cloth on Wednesdays",
    "Jupiter": "Donate yellow gram (chana dal), turmeric, or yellow cloth on Thursdays",
    "Venus":   "Donate white rice, white cloth, sugar, or dairy on Fridays",
    "Saturn":  "Donate black sesame (til), iron, dark blue cloth, or oil on Saturdays",
    "Rahu":    "Donate black sesame, blue/black cloth, coconut on Saturdays",
    "Ketu":    "Donate multi-coloured blankets, sesame, or donate to shelters on Thursdays",
}

# Fasting day for each planet
PLANET_FASTING = {
    "Sun":     "Fast on Sundays",
    "Moon":    "Fast on Mondays",
    "Mars":    "Fast on Tuesdays",
    "Mercury": "Fast on Wednesdays",
    "Jupiter": "Fast on Thursdays",
    "Venus":   "Fast on Fridays",
    "Saturn":  "Fast on Saturdays",
    "Rahu":    "Fast on Saturdays",
    "Ketu":    "Fast on Thursdays",
}

# Deity for each planet
PLANET_DEITY = {
    "Sun":     "Lord Surya / Lord Rama",
    "Moon":    "Lord Shiva / Goddess Parvati",
    "Mars":    "Lord Hanuman / Lord Kartikeya / Lord Subramanya",
    "Mercury": "Lord Vishnu / Lord Ganesha",
    "Jupiter": "Lord Vishnu / Lord Brihaspati / Guru",
    "Venus":   "Goddess Lakshmi / Goddess Saraswati",
    "Saturn":  "Lord Shani / Lord Hanuman",
    "Rahu":    "Goddess Durga / Lord Bhairava",
    "Ketu":    "Lord Ganesha / Lord Bhairava",
}

# Colour for each planet
PLANET_COLOUR = {
    "Sun":     "Orange / Gold / Red",
    "Moon":    "White / Silver / Light Blue",
    "Mars":    "Red / Coral",
    "Mercury": "Green / Emerald Green",
    "Jupiter": "Yellow / Golden Yellow",
    "Venus":   "White / Pink / Pastel",
    "Saturn":  "Dark Blue / Black / Violet",
    "Rahu":    "Smoky Grey / Electric Blue",
    "Ketu":    "Multi-colour / Spotted / Grey",
}

# Debilitation signs
DEBILITATED_SIGN = {
    "Sun":     "Libra",
    "Moon":    "Scorpio",
    "Mars":    "Cancer",
    "Mercury": "Pisces",
    "Jupiter": "Capricorn",
    "Venus":   "Virgo",
    "Saturn":  "Aries",
}

# Exalted signs
EXALTED_SIGN = {
    "Sun":     "Aries",
    "Moon":    "Taurus",
    "Mars":    "Capricorn",
    "Mercury": "Virgo",
    "Jupiter": "Cancer",
    "Venus":   "Pisces",
    "Saturn":  "Libra",
}

# Own signs
OWN_SIGNS = {
    "Sun":     {"Leo"},
    "Moon":    {"Cancer"},
    "Mars":    {"Aries", "Scorpio"},
    "Mercury": {"Gemini", "Virgo"},
    "Jupiter": {"Sagittarius", "Pisces"},
    "Venus":   {"Taurus", "Libra"},
    "Saturn":  {"Capricorn", "Aquarius"},
}

DUSTHANA = {6, 8, 12}

# Dosha-specific remedies
DOSHA_REMEDIES = {
    "mangal_dosha": {
        "title": "Mangal Dosha Remedies",
        "remedies": [
            "Recite Mangal (Mars) Beej Mantra: 'Om Kraam Kreem Kraum Sah Bhaumaya Namah' — 10000 times",
            "Visit Mangalnath Temple (Ujjain) or any Hanuman temple on Tuesdays",
            "Perform Kumbh Vivah (marriage to a peepal tree or idol) before wedding — reduces dosha",
            "Donate red lentils (masoor dal), red cloth on Tuesdays",
            "Wear Red Coral (Moonga) in gold/copper ring on right ring finger on Tuesday",
            "Fast on Tuesdays; eat only one meal",
            "Chant Hanuman Chalisa daily",
        ]
    },
    "kaal_sarp_dosha": {
        "title": "Kaal Sarp Dosha Remedies",
        "remedies": [
            "Perform Kaal Sarp Dosha Puja at Trimbakeshwar (Nashik) or Mahakaleshwar (Ujjain)",
            "Recite Maha Mrityunjaya Mantra 108 times daily",
            "Donate a silver serpent (nag-nagin) to a Shiva temple on Nag Panchami",
            "Wear a silver Kaal Sarp Dosha yantra or ring",
            "Chant 'Om Namah Shivaya' 108 times daily",
            "Observe fasting on Naag Panchami and perform Naag Puja",
            "Feed milk to a Shivalinga on Mondays",
        ]
    },
    "pitra_dosha": {
        "title": "Pitra Dosha Remedies",
        "remedies": [
            "Perform Pitru Tarpan (ancestral water offering) on every Amavasya (new moon)",
            "Perform Shradh and Pitru Paksha rituals annually in Ashwin month",
            "Donate food and clothes to Brahmins or the needy on Sundays",
            "Recite Gayatri Mantra 108 times daily",
            "Visit Gaya (Bihar) or Badrinath for Pitru Tarpan",
            "Plant a peepal tree and water it on Saturdays",
            "Feed crows (considered ancestors) and cows on Saturdays",
        ]
    },
    "guru_chandal_dosha": {
        "title": "Guru Chandal Dosha Remedies",
        "remedies": [
            "Recite Guru (Jupiter) mantra: 'Om Graam Greem Graum Sah Gurave Namah' — 16000 times",
            "Worship Lord Vishnu or Dakshinamurthy on Thursdays",
            "Donate yellow gram, turmeric, yellow cloth, or books on Thursdays",
            "Wear Yellow Sapphire (Pukhraj) in gold on the index finger on Thursday morning",
            "Respect your teachers, elders, and spiritual gurus",
            "Avoid speaking ill of gurus, parents, or religious figures",
            "Read and recite Vishnu Sahasranama regularly",
        ]
    },
    "grahan_dosha": {
        "title": "Grahan Dosha Remedies",
        "remedies": [
            "Perform Surya or Chandra Grahan Dosh Nivaran Puja",
            "Recite Aditya Hridayam Stotra for Surya Grahan Dosha",
            "Recite 'Om Som Somaya Namah' 11000 times for Chandra Grahan Dosha",
            "Donate wheat and jaggery (for Sun) or rice and silver (for Moon) on respective days",
            "Observe fast on Sundays (Surya) or Mondays (Chandra)",
            "Worship Lord Shiva with milk Abhishek on Mondays",
            "Avoid starting new ventures during eclipse periods",
        ]
    },
    "shani_dosha": {
        "title": "Shani Dosha Remedies",
        "remedies": [
            "Recite Shani Mantra: 'Om Praam Preem Praum Sah Shanaischaraya Namah' — 19000 times",
            "Visit Shani temple (Shingnapur or Tirunallar) on Saturdays",
            "Donate black sesame, mustard oil, iron, dark blue cloth on Saturdays",
            "Pour mustard oil on a Shani idol or iron statue on Saturdays",
            "Worship Lord Hanuman by reciting Hanuman Chalisa on Saturdays",
            "Wear Blue Sapphire (Neelam) or Amethyst — consult an astrologer first",
            "Feed black sesame mixed rice/roti to crows on Saturdays",
            "Light a sesame oil lamp at a Shani or Peepal tree on Saturday evenings",
        ]
    },
}

# Lagna lord table
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


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _planet_map(planets_data: list) -> dict:
    return {p["name"]: p for p in planets_data}


def _house_of(planet_name: str, d1: dict) -> int | None:
    for house_num, occupants in d1.items():
        for p in occupants:
            if p["name"] == planet_name:
                return int(house_num)
    return None


def _is_weak(planet: str, pm: dict, d1: dict) -> tuple[bool, str]:
    """
    Returns (is_weak, reason).
    Weak = debilitated, in enemy sign, or in dusthana.
    """
    if planet not in pm:
        return False, ""

    sign  = pm[planet]["zodiac"]
    house = _house_of(planet, d1)

    if sign == DEBILITATED_SIGN.get(planet):
        return True, f"Debilitated in {sign}"

    if house in DUSTHANA:
        return True, f"Placed in dusthana (house {house})"

    return False, ""


def _gemstone_recommendation(planet: str, reason: str, priority: str) -> dict:
    g = PLANET_GEMSTONE.get(planet, {})
    return {
        "planet":          planet,
        "priority":        priority,
        "reason":          reason,
        "primary_stone":   g.get("primary", ""),
        "secondary_stone": g.get("secondary", ""),
        "metal":           g.get("metal", ""),
        "finger":          g.get("finger", ""),
        "wear_day":        PLANET_WEAR_DAY.get(planet, ""),
        "note":            (
            "Always consult a qualified Vedic astrologer before wearing a gemstone. "
            "Test the stone for 3 days before final wearing."
        )
    }


def _planet_remedy(planet: str, reason: str) -> dict:
    return {
        "planet":    planet,
        "reason":    reason,
        "mantra":    PLANET_MANTRA.get(planet, {}).get("seed", ""),
        "count":     PLANET_MANTRA.get(planet, {}).get("count", ""),
        "charity":   PLANET_CHARITY.get(planet, ""),
        "fasting":   PLANET_FASTING.get(planet, ""),
        "deity":     PLANET_DEITY.get(planet, ""),
        "colour":    PLANET_COLOUR.get(planet, ""),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Master function
# ──────────────────────────────────────────────────────────────────────────────

def calculate_remedies(final_structure: dict) -> dict:
    """
    Main entry point.
    Pass the dict returned by generate_kundli().

    Returns a 'remedies' dict with gemstones, planet remedies,
    dosha remedies, and general remedies.
    """
    planets_data = final_structure.get("planets_data", [])
    house_mapper = final_structure.get("house_mapper", {})
    doshas       = final_structure.get("doshas", {})
    dasha_data   = final_structure.get("dasha", {})

    d1 = house_mapper.get("D1", {})
    pm = _planet_map(planets_data)

    gemstones        = []
    planet_remedies  = []
    dosha_remedies   = []
    seen_planets     = set()

    # ── 1. Lagna lord gemstone (always recommended) ───────────────────────────
    lagna = next((p for p in planets_data if p["name"] == "Ascendant"), None)
    lagna_sign = lagna["zodiac"] if lagna else None

    if lagna_sign:
        lagna_lord = SIGN_LORD.get(lagna_sign)
        if lagna_lord and lagna_lord not in seen_planets:
            gemstones.append(_gemstone_recommendation(
                lagna_lord,
                f"Lagna lord ({lagna_sign} Lagna) — strengthens overall health and personality",
                "Primary"
            ))
            planet_remedies.append(_planet_remedy(
                lagna_lord,
                f"Lagna lord of {lagna_sign} — always beneficial to strengthen"
            ))
            seen_planets.add(lagna_lord)

    # ── 2. Dasha lord gemstone ────────────────────────────────────────────────
    current_dasha = dasha_data.get("current", {})
    maha_lord  = current_dasha.get("mahadasha")
    antar_lord = current_dasha.get("antardasha")

    for planet, label in [(maha_lord, "Mahadasha lord"), (antar_lord, "Antardasha lord")]:
        if planet and planet not in seen_planets:
            # Only recommend if not a natural malefic causing problems
            gemstones.append(_gemstone_recommendation(
                planet,
                f"Current {label} — wearing its stone supports the dasha period",
                "Secondary"
            ))
            planet_remedies.append(_planet_remedy(
                planet,
                f"Current {label} — propitiate for dasha-period benefits"
            ))
            seen_planets.add(planet)

    # ── 3. Weak / afflicted planets ───────────────────────────────────────────
    PLANETS_TO_CHECK = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    for planet in PLANETS_TO_CHECK:
        weak, reason = _is_weak(planet, pm, d1)
        if weak and planet not in seen_planets:
            gemstones.append(_gemstone_recommendation(
                planet,
                f"Weak natal placement — {reason}",
                "Tertiary"
            ))
            planet_remedies.append(_planet_remedy(
                planet,
                f"Weak natal placement — {reason}"
            ))
            seen_planets.add(planet)

    # ── 4. Dosha-specific remedies ────────────────────────────────────────────
    for dosha_key, dosha_result in doshas.items():
        if str(dosha_result.get("present", "False")).lower() == "true":
            remedy_info = DOSHA_REMEDIES.get(dosha_key)
            if remedy_info:
                severity = dosha_result.get("severity", "Low")
                dosha_remedies.append({
                    "dosha":     dosha_key,
                    "title":     remedy_info["title"],
                    "severity":  severity,
                    "remedies":  remedy_info["remedies"],
                })

    # ── 5. General universal remedies ────────────────────────────────────────
    general_remedies = [
        {
            "category": "Daily Practice",
            "items": [
                "Recite Gayatri Mantra 108 times at sunrise",
                "Meditate for 15–20 minutes daily",
                "Observe Ekadashi (11th tithi) fasting monthly",
            ]
        },
        {
            "category": "Charity",
            "items": [
                "Feed cows and crows regularly",
                "Donate to orphanages or old-age homes on Saturdays",
                "Offer water to peepal tree on Saturdays",
            ]
        },
        {
            "category": "Spiritual",
            "items": [
                "Visit a temple of your Ishta Devata (chosen deity) regularly",
                "Light a ghee lamp in front of a Shiva Linga on Mondays",
                "Recite Hanuman Chalisa on Tuesdays and Saturdays",
            ]
        },
        {
            "category": "Lifestyle",
            "items": [
                "Wear colours associated with your Lagna lord and Dasha lord",
                "Avoid starting important work on inauspicious tithis (Amavasya, Chaturdashi)",
                "Perform Surya Namaskar (12 rounds) daily at sunrise",
            ]
        },
    ]

    return {
        "lagna":            lagna_sign,
        "lagna_lord":       SIGN_LORD.get(lagna_sign) if lagna_sign else None,
        "current_mahadasha": maha_lord,
        "current_antardasha": antar_lord,
        "gemstones":        gemstones,
        "planet_remedies":  planet_remedies,
        "dosha_remedies":   dosha_remedies,
        "general_remedies": general_remedies,
        "disclaimer": (
            "These remedies are based on classical Vedic astrology principles. "
            "Consult a qualified Jyotishi before wearing gemstones or undertaking major rituals. "
            "Remedies support; they do not replace personal effort and karma."
        )
    }
