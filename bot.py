import os
import yfinance as yf
from google.genai import Client
from google.genai import types
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import threading

# Flask setup for Render port binding
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = Client(api_key=GEMINI_API_KEY)

async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker_symbol = update.message.text.upper()
    await update.message.reply_text(f"⌛ מנתח את {ticker_symbol}...")

    try:
        # Fetch stock data
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="6mo")

        if df.empty:
            await update.message.reply_text(f"❌ לא מצאתי נתונים על {ticker_symbol}. וודא שהסימול נכון.")
            return

        # Technical Analysis using Gemini
        prompt = f"Analyze the following stock data for {ticker_symbol} from the last 6 months. Focus on support/resistance and trend: {df.tail(10).to_string()}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        # Plotting
        file_path = f"{ticker_symbol}.png"
        mpf.plot(df, type='candle', style='charles', title=f"{ticker_symbol} Analysis", savefig=file_path)

        await update.message.reply_photo(photo=open(file_path, 'rb'), caption=response.text)
        os.remove(file_path)

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("❌ קרתה שגיאה בניתוח המניה. וודא שהגדרת את ה-API KEY ב-Render.")

if __name__ == '__main__':
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Start Telegram Bot
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_stock))
    
    print("Bot is starting...")
    application.run_polling()
