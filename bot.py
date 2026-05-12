import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yfinance as yf
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

# ── Flask Server for Render Keep-Alive ────────────────────────────────────────
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "I am alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ── Logging & Config ──────────────────────────────────────────────────────────
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 שלום! שלח לי סימול מניה (למשל AAPL) לניתוח.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.upper().strip()
    wait_msg = await update.message.reply_text(f"🔍 מנתח את {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        price = stock.info.get('currentPrice', 'N/A')
        prompt = f"נתח בקצרה בעברית את מניית {ticker}. מחיר נוכחי: {price}. תן המלצה."
        response = model.generate_content(prompt)
        await wait_msg.edit_text(response.text)
    except Exception as e:
        await wait_msg.edit_text(f"שגיאה: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("Missing Tokens!")
        return

    keep_alive()  # מפעיל את השרת עבור Render

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
