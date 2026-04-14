from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Astrology API is running"}


@app.post("/kundli")
def generate_kundli(name: str, dob: str, lat: float, lon: float):
    if name and name.strip():
        if dob and dob.strip():
            if check_positive_number(lat):
                if check_positive_number(lon):
                    return "hello astrology"
                else:
                    return "Please enter a valid longitude 😭!! to proceed..."
            else:
                return "Please enter a valid latitude 😭!! to proceed..."

        else:
            return "Please enter your date of birth 😭!! to proceed..."

    else:
        return "Please enter your name 😭!! to proceed..."


def check_positive_number(val):
    # Check if it's an instance of int or float
    if isinstance(val, (int, float)) and val > 0:
        if isinstance(val, int) or val.is_integer():
            return "Positive Integer"
        else:
            return "Positive Float"
    return "Not a Positive Number"
