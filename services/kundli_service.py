from datetime import datetime

from utils import config
from utils.core_logic import validate_parameters, convert_ist_to_utc, get_planet_data, build_house_map, update_json, \
    get_house_mapper, calculate_all_dashas, get_current_dasha, get_tithi, get_sunrise_sunset
import swisseph as swe
import os
import json

from utils.dosha_calculator import calculate_doshas
from utils.yoga_calculator import calculate_yogas

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

        sunrise_data = get_sunrise_sunset(year, month, day, lat,lon)
        parts = sunrise_data["sunrise"].split(":")
        sunrise_utc = int(parts[0]) + int(parts[1])/60.0 - 5.5
        jd_sunrise = swe.julday(year, month, day,float(sunrise_utc))
        tithi_data = get_tithi(jd_sunrise)

        details = {
            "name": name,
            "date_of_birth": date_str,
            "time_of_birth": birth_time,
            "lat": lat,
            "lon": lon,
            "sunrise": sunrise_data["sunrise"],
            "sunset": sunrise_data["sunset"],
            "tithi" : tithi_data

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

        # ------------ dasha analysis-------
        moon = next(p for p in planet_data if p["name"] == "Moon")

        all_dashas = calculate_all_dashas(
            date_str,
            birth_time,
            moon["longitude"]  # full longitude, not degree_in_rashi
        )

        current = get_current_dasha(all_dashas)

        update_json("dasha", {
            "current": current,
            "all_mahadashas": all_dashas
        })

        #--- dosha calculation

        doshas = calculate_doshas(config.final_structure)
        config.final_structure["doshas"] = doshas

       #-- yoga calculator

        config.final_structure["yogas"] = calculate_yogas(config.final_structure)

        return config.final_structure

