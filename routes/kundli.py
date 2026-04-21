from fastapi import APIRouter
from services.kundli_service import generate_kundli
router = APIRouter()

@router.post("/kundli")
def kundli_route(name: str, dob: str,birth_time:str, lat: float, lon: float):
    return generate_kundli(name, dob,birth_time, lat, lon)


if __name__ == "__main__":
    data = kundli_route("deepak","09-01-1997","23.49",22.03,85.37)
    print(data)