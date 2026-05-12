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
matplotlib.use('Agg') # חיוני לעבודה בשרת ללא מסך
import matplotlib.pyplot as plt
import io

# ── שרת Flask קטן כדי ש-Render לא יכבה את הבוט ──────────────────────────
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    # Render מעביר אוטומטית את הפורט במשתנה הסביבה PORT
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ── הגדרות לוגים ומפתחות ────────────────────────────────────────────────
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# הגדרת Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ── פונקציות עזר ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ברוכים הבאים! שלחו לי סימול מניה (למשל: AAPL, TSLA, NVDA) ואני אנתח אותה עבורכם.")

async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker_symbol = update.message.text.upper().strip()
    
    # הודעת המתנה
    status_msg = await update.message.reply_text(f"⏳ מנתח את {ticker_symbol}, רק רגע...")

    try:
        # 1. משיכת נתונים מ-yfinance
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="1mo")
        
        if hist.empty:
            await status_msg.edit_text("❌ לא מצאתי נתונים על הסימול הזה. וודאו שהסימול נכון (למשל AAPL).")
            return

        current_price = hist['Close'].iloc[-1]
        change = ((current_price - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100

        # 2. יצירת גרף
        plt.figure(figsize=(10, 5))
        plt.plot(hist['Close'], color='blue', linewidth=2)
        plt.title(f"{ticker_symbol} - Last 30 Days")
        plt.grid(True, alpha=0.3)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        # 3. ניתוח עם Gemini
        prompt = f"""
        Analyze the stock {ticker_symbol} in Hebrew.
        Current price: {current_price:.2f}$
        Monthly change: {change:.2f}%
        Provide a very brief technical summary and a 'Sentiment' (Positive/Neutral/Negative).
        Keep it professional and concise.
        """
        response = gemini_model.generate_content(prompt)
        analysis_text = response.text

        # 4. שליחת התוצאות
        await update.message.reply_photo(photo=buf, caption=f"📊 **ניתוח מניית {ticker_symbol}**\n\n{analysis_text}")
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text(f"😔 קרתה שגיאה בניתוח המניה. נסו שוב מאוחר יותר.")

# ── הרצה ראשית ─────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logging.error("Missing Environment Variables!")
        return

    # הפעלת שרת ה-Keep Alive
    keep_alive()

    # הגדרת הבוט
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_stock))

    logging.info("🚀 הבוט התחיל לעבוד!")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
