from datetime import datetime

from utils.core_logic import validate_parameters, convert_ist_to_utc, get_planet_data, build_house_map
import swisseph as swe
import os

# This works both locally AND on Render
# Go one level UP from /services to reach project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)


def generate_kundli(name: str, date_str: str, birth_time: str, lat: float, lon: float):
    if validate_parameters(name, date_str, lat, lon):
        # Set sidereal mode to Lahiri (standard in Vedic astrology)
        swe.set_sid_mode(swe.SIDM_LAHIRI)

        # Parse the string into a datetime object
        date_obj = datetime.strptime(date_str, '%d-%m-%Y')

        # Extract components
        day = date_obj.day
        month = date_obj.month
        year = date_obj.year

        parts = str(birth_time).split('.')
        ist_hr = int(parts[0])
        ist_min = int(parts[1])

        utc_decimal = convert_ist_to_utc(ist_hr, ist_min)
        # Julian Day in UT
        jd_ut = swe.julday(year, month, day, utc_decimal)

        planet_data = get_planet_data(jd_ut, year, month, day, ist_hr, ist_min, lat, lon)
        #return planet_data

        house_mapper = build_house_map(planet_data)
        return house_mapper
