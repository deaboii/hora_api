import swisseph as swe
import os

# This works both locally AND on Render
# Go one level UP from /services to reach project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)
# Planets to calculate
planets = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Rahu": swe.TRUE_NODE,   # Rahu
    "Ketu": swe.TRUE_NODE    # Ketu will be 180° from Rahu
}

# Zodiac signs
signs = [
    'Aries',
    'Taurus',
    'Gemini',
    'Cancer',
    'Leo',
    'Virgo',
    'Libra',
    'Scorpio',
    'Sagittarius',
    'Capricorn',
    'Aquarius',
    'Pisces'
]

# Nakshatras
nakshatras = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati"
]
# Vimshottari Dasha sequence - planet: total years
DASHA_SEQUENCE = [
    ("Ketu",    7),
    ("Venus",   20),
    ("Sun",     6),
    ("Moon",    10),
    ("Mars",    7),
    ("Rahu",    18),
    ("Jupiter", 16),
    ("Saturn",  19),
    ("Mercury", 17),
]

# Which planet rules which Nakshatra (27 nakshatras, repeating sequence)
NAKSHATRA_LORDS = [
    "Ketu",    # Ashwini
    "Venus",   # Bharani
    "Sun",     # Krittika
    "Moon",    # Rohini
    "Mars",    # Mrigashira
    "Rahu",    # Ardra
    "Jupiter", # Punarvasu
    "Saturn",  # Pushya
    "Mercury", # Ashlesha
    "Ketu",    # Magha
    "Venus",   # Purva Phalguni
    "Sun",     # Uttara Phalguni
    "Moon",    # Hasta
    "Mars",    # Chitra
    "Rahu",    # Swati
    "Jupiter", # Vishakha
    "Saturn",  # Anuradha
    "Mercury", # Jyeshtha
    "Ketu",    # Mula
    "Venus",   # Purva Ashadha
    "Sun",     # Uttara Ashadha
    "Moon",    # Shravana
    "Mars",    # Dhanishta
    "Rahu",    # Shatabhisha
    "Jupiter", # Purva Bhadrapada
    "Saturn",  # Uttara Bhadrapada
    "Mercury", # Revati
]


final_structure = {}
