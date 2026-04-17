from fastapi import FastAPI
from pydantic import BaseModel
from routes.kundli import router as kundli_router
app = FastAPI()
app.include_router(kundli_router)
@app.get("/")
def home():
    return {"message": "Astrology API is running"}