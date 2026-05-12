import os
import yfinance as yf
from google.genai import Client
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from flask import Flask
import threading

# Flask setup for Render
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is Alive", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = Client(api_key=GEMINI_API_KEY)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker_symbol = update.message.text.upper()
    
    # בדיקת חיבור בסיסית
    if ticker_symbol == "היי":
        await update.message.reply_text("🚀 הבוט מחובר! שלח לי סימול מניה (לדוגמה: NVDA)")
        return

    await update.message.reply_text(f"⌛ מנתח את {ticker_symbol}...")

    try:
        # משיכת נתונים
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="6mo")

        if df.empty:
            await update.message.reply_text(f"❌ לא מצאתי נתונים על {ticker_symbol}. וודא שהסימול נכון.")
            return

        # ניתוח טכני בעזרת Gemini (מודל 1.5 ליציבות)
        prompt = f"Analyze the following stock data for {ticker_symbol} from the last 6 months. Focus on support/resistance and trend: {df.tail(10).to_string()}"
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        
        # יצירת הגרף
        file_path = f"{ticker_symbol}.png"
        mpf.plot(df, type='candle', style='charles', title=f"{ticker_symbol} - 6 Months", savefig=file_path)

        # שליחת התמונה עם הניתוח
        await update.message.reply_photo(photo=open(file_path, 'rb'), caption=response.text[:1024])
        os.remove(file_path)

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            await update.message.reply_text("❌ גוגל חוסמת את הבקשה עקב עומס (429). נסה שוב בעוד דקה.")
        else:
            await update.message.reply_text(f"❌ קרתה שגיאה: {error_msg}")

if __name__ == '__main__':
    # הרצת Flask ברקע עבור Render
    threading.Thread(target=run_flask, daemon=True).start()
    
    # הרצת הבוט
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is starting...")
    application.run_polling()
