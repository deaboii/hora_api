from fastapi import FastAPI, Request
import requests
from routes.kundli import router as kundli_router

import os

app = FastAPI()
app.include_router(kundli_router)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.get("/")
def home():
    return {"message": "Astrology API is running"}

@app.post("/webhook/astro123")
async def telegram_webhook(req: Request):
    data = await req.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            reply = "Welcome! Enter your birth date (YYYY-MM-DD)"
        else:
            try:
                # res = requests.post(
                #     "https://hora-api-v46s.onrender.com/predict",
                #     headers={"x-api-key": "YOUR_SECRET_KEY"},
                #     json={"input": text}
                # )
                # reply = res.json().get("prediction", "Couldn't generate prediction")
                reply = "Hii baby"

            except:
                reply = "Error connecting to astrology service"

        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply
            }
        )

    return {"ok": True}