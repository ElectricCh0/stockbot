import os
import logging
import io
from threading import Thread
from flask import Flask
import yfinance as yf
from genai import Client # הספרייה החדשה
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Flask Server ---
app_flask = Flask('')
@app_flask.route('/')
def home(): return "Bot is Alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

# --- Config ---
logging.basicConfig(level=logging.INFO)
# הגדרה חדשה ל-Gemini
client = Client(api_key=os.environ.get("GEMINI_API_KEY"))

def create_chart(df, ticker):
    buf = io.BytesIO()
    mpf.plot(df, type='candle', style='charles', title=ticker, savefig=buf)
    buf.seek(0)
    return buf

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.upper().strip()
    
    # אם זה סימול מניה (מילה אחת באנגלית)
    if user_text.isalpha() and len(user_text) <= 5:
        try:
            status = await update.message.reply_text(f"⏳ מנתח את {user_text}...")
            stock = yf.Ticker(user_text)
            hist = stock.history(period="3mo")
            
            if hist.empty:
                await status.edit_text("❌ לא מצאתי נתונים.")
                return

            # יצירת גרף
            chart = create_chart(hist, user_text)
            
            # ניתוח טקסטואלי
            prompt = f"נתח בקצרה את מניית {user_text}. מחיר אחרון: {hist['Close'].iloc[-1]:.2f}$"
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            await update.message.reply_photo(photo=chart, caption=response.text)
            await status.delete()
        except Exception as e:
            logging.error(e)
            await update.message.reply_text("קרתה שגיאה בשליפת הנתונים.")
    else:
        # שיחה רגילה
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=user_text + " (ענה בעברית)")
            await update.message.reply_text(response.text)
        except:
            await update.message.reply_text("אני מתקשה להבין כרגע...")

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
