import json

from utils import config
from utils.config import planets, signs, nakshatras
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


def update_json(node, data):
    if node == "details":
        config.final_structure = {
            "details": data
        }
    if node == "planets_data":
        config.final_structure["planets_data"] = data

    if node == "house_mapper":
        config.final_structure["house_mapper"] = data

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
