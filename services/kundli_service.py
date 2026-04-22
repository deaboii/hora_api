from datetime import datetime

from utils import config
from utils.core_logic import validate_parameters, convert_ist_to_utc, get_planet_data, build_house_map, update_json, \
    get_house_mapper
import swisseph as swe
import os
import json

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

        details = {
            "name": name,
            "date_of_birth": date_str,
            "time_of_birth": birth_time,
            "lat": lat,
            "lon": lon
        }
        # update_json_with_details
        update_json("details", details)

        planet_data = get_planet_data(jd_ut, year, month, day, ist_hr, ist_min, lat, lon)

        # update_json_with_planet_data
        update_json("planets_data", planet_data)

        # house_mapper = build_house_map(planet_data)
        # update_json_with_D1_data
        # return update_json("house_mapper", {"D1": house_mapper})

        d1 = get_house_mapper(config.final_structure["planets_data"], "D1")
        d9 = get_house_mapper(config.final_structure["planets_data"], "D9")
        d10 = get_house_mapper(config.final_structure["planets_data"], "D10")

        update_json("house_mapper", {**d1, **d9, **d10})

        return config.final_structure
