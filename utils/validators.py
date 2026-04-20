from base import planets, signs, nakshatras
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
def get_planet_data(jd_ut,year,month,day,ist_hour, ist_minute,latitude, longitude ):
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