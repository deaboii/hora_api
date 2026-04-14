from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Request body
class BirthDetails(BaseModel):
    date: str
    time: str
    lat: float
    lon: float

@app.get("/")
def home():
    return {"message": "Astrology API is running"}


@app.post("/kundli")
def generate_kundli(data: BirthDetails):
    result = "Hi"
    return {"kundli": result}