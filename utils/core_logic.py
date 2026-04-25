import json
from datetime import datetime, timedelta

from utils import config
from utils.config import planets, signs, nakshatras, DASHA_SEQUENCE, NAKSHATRA_LORDS, TITHI_NAMES
import swisseph as swe
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)


def check_positive_number(val):
    # Check if it's an instance of int or float
    if isinstance(val, (int, float)) and val > 0:
        if isinstance(val, int) or val.is_integer():
            return True
        else:
            return True
    return False


def validate_parameters(name, dob, lat, lon):
    if name and name.strip():
        if dob and dob.strip():
            if check_positive_number(lat):
                if check_positive_number(lon):
                    return True
                else:
                    return "Please enter a valid longitude 😭!! to proceed..."
            else:
                return "Please enter a valid latitude 😭!! to proceed..."

        else:
            return "Please enter your date of birth 😭!! to proceed..."

    else:
        return "Please enter your name 😭!! to proceed..."


def convert_ist_to_utc(ist_hour, ist_minute):
    total_ist_minutes = ist_hour * 60 + ist_minute
    total_utc_minutes = total_ist_minutes - 330  # Subtract 5 hours 30 minutes
    utc_hour = total_utc_minutes // 60
    utc_minute = total_utc_minutes % 60
    utc_decimal = utc_hour + utc_minute / 60
    return utc_decimal


def get_planet_data(jd_ut, year, month, day, ist_hour, ist_minute, latitude, longitude):
    planet_data = []

    for name, pl in planets.items():
        lon = swe.calc_ut(jd_ut, pl, swe.FLG_SIDEREAL)[0][0]

        # Ketu is 180 degrees opposite to Rahu
        if name == "Ketu":
            lon = (lon + 180.0) % 360.0

        sign, nak, pada, degree_in_rashi, degree_in_nakshatra = interpret_position(lon)

        planet_data.append({
            "name": name,
            "longitude": round(lon, 6),
            "zodiac": sign,
            "degree_in_rashi": round(degree_in_rashi, 4),
            "Nakshatra": nak,
            "degree_in_nakshatra": round(degree_in_nakshatra, 4),
            "Pada": pada
        })

    # Ascendant calculation
    jd_lmt = swe.julday(year, month, day, ist_hour + ist_minute / 60.0)
    _, ascmc = swe.houses_ex(jd_ut, latitude, longitude, b'A', swe.FLG_SIDEREAL)
    asc_deg = ascmc[0]  # Ascendant longitude

    asc_sign, asc_nak, asc_pada, asc_degree_in_rashi, asc_degree_in_nakshatra = interpret_position(asc_deg)
    planet_data.append({
        "name": "Ascendant",
        "longitude": round(asc_deg, 6),
        "zodiac": asc_sign,
        "degree_in_rashi": round(asc_degree_in_rashi, 4),
        "Nakshatra": asc_nak,
        "degree_in_nakshatra": round(asc_degree_in_nakshatra, 4),
        "Pada": asc_pada
    })

    return planet_data


def interpret_position(degree):
    # Zodiac sign
    sign_index = int(degree // 30)
    sign = signs[sign_index]
    degree_in_rashi = degree % 30

    # Nakshatra and pada
    nak_index = int(degree // 13.3333333)
    nak = nakshatras[nak_index]
    degree_in_nakshatra = degree % 13.3333333
    pada = int(degree_in_nakshatra // 3.3333333) + 1

    return sign, nak, pada, degree_in_rashi, degree_in_nakshatra


def get_house_number(lagna, planet_sign):
    lagna_index = signs.index(lagna)
    planet_index = signs.index(planet_sign)

    return (planet_index - lagna_index) % 12 + 1


def build_house_map(chart_data):
    house_map = {i: [] for i in range(1, 13)}

    # get lagna
    lagna = None
    for p in chart_data:
        if p["name"] == "Ascendant":
            lagna = p["zodiac"]
            break

    # assign planets to houses
    for p in chart_data:
        sign = p["zodiac"]
        house = get_house_number(lagna, sign)

        house_map[house].append({
            "name": p["name"],
            "sign": sign,
            "degree": round(p["degree_in_rashi"], 3)
        })

    return house_map


# ----------- update final json ---------------
def update_json(node, data):
    if node == "details":
        config.final_structure = {
            "details": data
        }
    if node == "planets_data":
        config.final_structure["planets_data"] = data

    if node == "house_mapper":
        config.final_structure["house_mapper"] = data

    if node == "dasha":
        config.final_structure["dasha"] = data
    # Convert to JSON string
    return json.dumps(config.final_structure)


SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

# Starting sign index for each D9 element group
D9_START = {
    "fire": 0,  # Aries
    "earth": 9,  # Capricorn
    "air": 6,  # Libra
    "water": 3,  # Cancer
}

SIGN_ELEMENT = {
    "Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
    "Taurus": "earth", "Virgo": "earth", "Capricorn": "earth",
    "Gemini": "air", "Libra": "air", "Aquarius": "air",
    "Cancer": "water", "Scorpio": "water", "Pisces": "water",
}

CHART_DIVISIONS = {
    "D1": 1,
    "D9": 9,
    "D10": 10,
    "D12": 12,
    "D7": 7,
    "D2": 2,
    "D3": 3,
    "D4": 4,
}


def get_divisional_sign(zodiac, degree_in_rashi, chart_type):
    """Get the divisional chart sign for a planet."""
    divisions = CHART_DIVISIONS[chart_type]
    part_size = 30.0 / divisions
    slot = int(degree_in_rashi / part_size)  # 0-indexed slot

    if chart_type == "D1":
        return zodiac

    elif chart_type == "D9":
        element = SIGN_ELEMENT[zodiac]
        start = D9_START[element]
        d9_sign_index = (start + slot) % 12
        return signs[d9_sign_index]

    elif chart_type in ("D10", "D12", "D7", "D2", "D3", "D4"):
        # Generic: odd signs start from same sign, even signs start from 9th
        sign_index = SIGN_INDEX[zodiac]
        if sign_index % 2 == 0:  # odd sign (Aries=0, Gemini=2...)
            start = sign_index
        else:  # even sign
            start = (sign_index + 8) % 12  # 9th from sign
        div_sign_index = (start + slot) % 12
        return signs[div_sign_index]

    return zodiac


def get_house_mapper(planets_data, chart_type):
    """
    Takes planets_data list and chart_type string.
    Returns house_mapper dict like your existing API response.
    """
    # Step 1: Get divisional sign for each planet
    planet_div_signs = []
    ascendant_div_sign = None

    for planet in planets_data:
        div_sign = get_divisional_sign(
            planet["zodiac"],
            planet["degree_in_rashi"],
            chart_type
        )
        planet_div_signs.append({
            "name": planet["name"],
            "sign": div_sign,
            "degree": round(planet["degree_in_rashi"], 3)
        })
        if planet["name"] == "Ascendant":
            ascendant_div_sign = div_sign

    # Step 2: Build house map using Ascendant as House 1
    asc_index = SIGN_INDEX[ascendant_div_sign]
    house_map = {str(i): [] for i in range(1, 13)}

    for p in planet_div_signs:
        if p["name"] == "Ascendant":
            continue  # optionally skip or include
        sign_index = SIGN_INDEX[p["sign"]]
        house_number = ((sign_index - asc_index) % 12) + 1
        house_map[str(house_number)].append(p)

    return {chart_type: house_map}


# -------------------------Dasha Analysis-------------------


NAKSHATRA_SPAN = 13.3333333  # degrees per nakshatra
PADA_SPAN = 3.3333333  # degrees per pada


def get_dasha_balance_at_birth(moon_longitude):
    """
    Calculate how much of the birth Dasha was remaining at birth.
    Based on Moon's exact position within its nakshatra.
    """
    nak_index = int(moon_longitude // NAKSHATRA_SPAN)
    ruling_planet = NAKSHATRA_LORDS[nak_index]

    # How far Moon has travelled inside this nakshatra
    degree_in_nak = moon_longitude % NAKSHATRA_SPAN

    # Fraction REMAINING in this nakshatra
    fraction_remaining = (NAKSHATRA_SPAN - degree_in_nak) / NAKSHATRA_SPAN

    # Find total years for this planet's dasha
    total_years = dict(DASHA_SEQUENCE)[ruling_planet]

    # Years remaining at birth
    years_remaining = fraction_remaining * total_years

    return ruling_planet, years_remaining


def calculate_all_dashas(dob_str, birth_time_str, moon_longitude):
    """
    Calculate all Mahadashas, Antardashas, Pratyantar Dashas.

    dob_str: "09-01-1997"
    birth_time_str: "23.49"
    moon_longitude: from planets_data (Moon's longitude)
    """

    # Parse birth datetime
    parts = birth_time_str.split(".")
    hour = int(parts[0])
    minute = int(parts[1])
    birth_dt = datetime.strptime(dob_str, "%d-%m-%Y").replace(
        hour=hour, minute=minute
    )

    # Get starting dasha and balance
    start_planet, years_remaining = get_dasha_balance_at_birth(moon_longitude)

    # Build full dasha sequence starting from birth planet
    sequence_names = [p for p, _ in DASHA_SEQUENCE]
    start_index = sequence_names.index(start_planet)

    # Reorder sequence from birth planet
    ordered_sequence = (
            DASHA_SEQUENCE[start_index:] + DASHA_SEQUENCE[:start_index]
    )

    all_dashas = []
    current_date = birth_dt

    for i, (maha_planet, maha_years) in enumerate(ordered_sequence):

        # First dasha uses remaining years, rest use full years
        actual_maha_years = years_remaining if i == 0 else maha_years
        maha_end = current_date + timedelta(days=actual_maha_years * 365.25)

        # --- Antardasha calculation ---
        antardashas = []
        antar_start = current_date
        antar_index = i % len(DASHA_SEQUENCE)

        for j in range(9):
            antar_planet, antar_full_years = DASHA_SEQUENCE[
                (antar_index + j) % len(DASHA_SEQUENCE)
                ]

            # Antardasha duration = (maha_years * antar_years) / 120
            antar_years = (actual_maha_years * antar_full_years) / 120
            antar_end = antar_start + timedelta(days=antar_years * 365.25)

            # --- Pratyantar Dasha ---
            pratyantars = []
            prat_start = antar_start

            for k in range(9):
                prat_planet, prat_full_years = DASHA_SEQUENCE[
                    (antar_index + j + k) % len(DASHA_SEQUENCE)
                    ]
                prat_years = (antar_years * prat_full_years) / 120
                prat_end = prat_start + timedelta(days=prat_years * 365.25)

                pratyantars.append({
                    "planet": prat_planet,
                    "start": prat_start.strftime("%d-%m-%Y"),
                    "end": prat_end.strftime("%d-%m-%Y"),
                })
                prat_start = prat_end

            antardashas.append({
                "planet": antar_planet,
                "start": antar_start.strftime("%d-%m-%Y"),
                "end": antar_end.strftime("%d-%m-%Y"),
                "pratyantar": pratyantars
            })
            antar_start = antar_end

        all_dashas.append({
            "planet": maha_planet,
            "start": current_date.strftime("%d-%m-%Y"),
            "end": maha_end.strftime("%d-%m-%Y"),
            "antardasha": antardashas
        })
        current_date = maha_end

    return all_dashas


def get_current_dasha(all_dashas):
    """Find which Maha, Antar, Pratyantar dasha is active today."""
    today = datetime.today()

    for maha in all_dashas:
        maha_start = datetime.strptime(maha["start"], "%d-%m-%Y")
        maha_end = datetime.strptime(maha["end"], "%d-%m-%Y")

        if maha_start <= today <= maha_end:
            current_maha = maha["planet"]

            for antar in maha["antardasha"]:
                antar_start = datetime.strptime(antar["start"], "%d-%m-%Y")
                antar_end = datetime.strptime(antar["end"], "%d-%m-%Y")

                if antar_start <= today <= antar_end:
                    current_antar = antar["planet"]

                    for prat in antar["pratyantar"]:
                        prat_start = datetime.strptime(prat["start"], "%d-%m-%Y")
                        prat_end = datetime.strptime(prat["end"], "%d-%m-%Y")

                        if prat_start <= today <= prat_end:
                            return {
                                "mahadasha": current_maha,
                                "antardasha": current_antar,
                                "pratyantar": prat["planet"],
                                "pratyantar_end": prat["end"]
                            }
    return {}


# ─────────────────────────────────────────────
# SUNRISE
# ─────────────────────────────────────────────
def get_sunrise_sunset(year, month, day, lat, lon):
    jd = swe.julday(year, month, day, 0.0)
    geopos = (lon, lat, 0)

    _, tret_rise = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE, geopos)
    _, tret_set = swe.rise_trans(jd, swe.SUN, swe.CALC_SET, geopos)

    def to_ist(h_utc):
        h_ist = h_utc + 5.5
        if h_ist >= 24:
            h_ist -= 24
        hour = int(h_ist)
        minute = int((h_ist - hour) * 60)
        return f"{hour:02d}:{minute:02d}"

    _, _, _, h_rise = swe.revjul(tret_rise[0])
    _, _, _, h_set = swe.revjul(tret_set[0])

    return {
        "sunrise": to_ist(h_rise),
        "sunset": to_ist(h_set)
    }
# ─────────────────────────────────────────────
# TITHI
# ─────────────────────────────────────────────

def get_tithi(jd_ut):
    """
    Calculate Tithi (lunar day) from a Julian Day (UT).
    Returns tithi number (1–30), name, paksha (Shukla/Krishna), and
    the Moon–Sun angular difference that produced it.
    """
    # Tropical longitudes for Moon and Sun
    sun_lon  = swe.calc_ut(jd_ut, swe.SUN,  swe.FLG_SWIEPH)[0][0]
    moon_lon = swe.calc_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)[0][0]

    # Angular difference (Moon ahead of Sun)
    diff = (moon_lon - sun_lon) % 360.0

    # Each tithi spans 12°
    tithi_number = int(diff / 12.0) + 1   # 1–30

    # Paksha
    paksha = "Shukla" if tithi_number <= 15 else "Krishna"

    # Name index (1–15 repeats for both pakshas)
    name_index = (tithi_number - 1) % 15   # 0–14
    tithi_name = TITHI_NAMES[name_index]

    # Special override for 15th tithis
    if tithi_number == 15:
        tithi_name = "Purnima"
    elif tithi_number == 30:
        tithi_name = "Amavasya"

    return {
        "tithi_number": tithi_number,
        "tithi_name": tithi_name,
        "paksha": paksha,
        "moon_sun_diff": round(diff, 4)
    }
