from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Astrology API is running"}


@app.post("/kundli")
def generate_kundli(name: str,dob: str,lat: float, lon: float):
    return {"kundli": name + dob }