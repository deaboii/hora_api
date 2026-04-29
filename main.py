from fastapi import FastAPI
from pydantic import BaseModel
from routes.kundli import router as kundli_router
app = FastAPI()
app.include_router(kundli_router)

BOT_TOKEN ="8746488719:AAFx0CeX5ZEOT2y2v-QxgEV9TAZ9sKGVS10"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.get("/")
def home():
    return {"message": "Astrology API is running"}

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            reply = "Welcome! Enter your birth date (YYYY-MM-DD)"
        else:
            # Call your astrology API
            try:
                res = requests.post(
                    "https://your-api.onrender.com/predict",
                    json={"input": text}
                )
                reply = res.json().get("prediction", "Couldn't generate prediction")
            except:
                reply = "Error connecting to astrology service"

        # Send reply
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply
            }
        )

    return {"ok": True}