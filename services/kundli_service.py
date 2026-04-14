from utils.validators import validate_parameters


def generate_kundli(name: str, dob: str, lat: float, lon: float):
    validate_parameters(name,dob,lat,lon)
