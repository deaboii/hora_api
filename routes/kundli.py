from fastapi import APIRouter
from services.kundli_service import generate_kundli
router = APIRouter()

@router.post("/kundli")
def kundli_route(name: str, dob: str, lat: float, lon: float):
    return generate_kundli(name, dob, lat, lon)
